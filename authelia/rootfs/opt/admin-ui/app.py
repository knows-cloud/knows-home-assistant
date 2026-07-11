"""Admin UI for the Better Authelia Home Assistant addon.

Served through Home Assistant ingress on port 8099. Reads and writes the
Authelia configuration and users database in /config and controls the
Authelia s6 service to apply changes.
"""

import json
import os
import re
import secrets as pysecrets
import shutil
import subprocess
import urllib.request

import yaml
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

CONFIG_PATH = os.environ.get("AUTHELIA_CONFIG", "/config/configuration.yml")
USERS_PATH = os.environ.get("AUTHELIA_USERS", "/config/users_database.yml")
ASSETS_DIR = os.environ.get("AUTHELIA_ASSETS", "/config/assets")
SECRETS_DIR = "/config/secrets"
RESTART_FLAG = "/tmp/authelia_restart_needed"
SERVICE_DIR = "/run/service/authelia"
HEALTH_URL = "http://127.0.0.1:9091/api/health"

THEMES = ["light", "dark", "grey", "auto"]
POLICIES = ["bypass", "one_factor", "two_factor", "deny"]
LOG_LEVELS = ["trace", "debug", "info", "warn", "error"]

app = Flask(__name__)
app.secret_key = pysecrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


class IngressMiddleware:
    """Honour the X-Ingress-Path header so url_for() builds ingress URLs."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_INGRESS_PATH", "")
        if prefix:
            environ["SCRIPT_NAME"] = prefix
            path = environ.get("PATH_INFO", "")
            if path.startswith(prefix):
                environ["PATH_INFO"] = path[len(prefix):] or "/"
        return self.wsgi_app(environ, start_response)


app.wsgi_app = IngressMiddleware(app.wsgi_app)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def save_config(config):
    if os.path.exists(CONFIG_PATH):
        shutil.copy2(CONFIG_PATH, CONFIG_PATH + ".bak")
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, default_flow_style=False, sort_keys=False,
                       allow_unicode=True)
    mark_restart_needed()


def load_users():
    try:
        with open(USERS_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        data = {}
    data.setdefault("users", {})
    if data["users"] is None:
        data["users"] = {}
    return data


def save_users(data):
    if os.path.exists(USERS_PATH):
        shutil.copy2(USERS_PATH, USERS_PATH + ".bak")
    with open(USERS_PATH, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=True,
                       allow_unicode=True)
    os.chmod(USERS_PATH, 0o600)
    mark_restart_needed()


def dig(config, *keys, default=None):
    node = config
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def first_cookie(config):
    cookies = dig(config, "session", "cookies", default=None)
    if isinstance(cookies, list) and cookies and isinstance(cookies[0], dict):
        return cookies[0]
    return {}


def authelia_env():
    env = dict(os.environ)
    env.update({
        "AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE":
            os.path.join(SECRETS_DIR, "jwt_secret"),
        "AUTHELIA_SESSION_SECRET_FILE":
            os.path.join(SECRETS_DIR, "session_secret"),
        "AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE":
            os.path.join(SECRETS_DIR, "storage_encryption_key"),
    })
    return env


def validate_config_file(path):
    """Run `authelia validate-config`; returns (ok, output)."""
    try:
        proc = subprocess.run(
            ["authelia", "validate-config", "--config", path],
            capture_output=True, text=True, timeout=30, env=authelia_env(),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, output.strip()
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        return False, str(exc)


def hash_password(password):
    proc = subprocess.run(
        ["authelia", "crypto", "hash", "generate", "argon2",
         "--password", password],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "hashing failed")
    match = re.search(r"Digest:\s*(\S+)", proc.stdout)
    if not match:
        raise RuntimeError("could not parse password digest")
    return match.group(1)


def mark_restart_needed():
    with open(RESTART_FLAG, "w", encoding="utf-8") as fh:
        fh.write("1")


def clear_restart_needed():
    try:
        os.remove(RESTART_FLAG)
    except FileNotFoundError:
        pass


def restart_authelia():
    for svc in ("/command/s6-svc", "s6-svc"):
        try:
            proc = subprocess.run([svc, "-r", SERVICE_DIR],
                                  capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                clear_restart_needed()
                return True, ""
            error = proc.stderr.strip()
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        return False, error
    return False, "s6-svc not found"


def authelia_status():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
            body = json.loads(resp.read().decode())
            return "running" if body.get("status") == "OK" else "unhealthy"
    except Exception:  # noqa: BLE001
        return "stopped"


def authelia_version():
    try:
        proc = subprocess.run(["authelia", "build-info"],
                              capture_output=True, text=True, timeout=10)
        match = re.search(r"Version:\s*(\S+)", proc.stdout)
        return match.group(1) if match else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


@app.context_processor
def inject_globals():
    return {
        "restart_needed": os.path.exists(RESTART_FLAG),
        "themes": THEMES,
        "policies": POLICIES,
        "log_levels": LOG_LEVELS,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    config = load_config()
    users = load_users()["users"]
    cookie = first_cookie(config)
    rules = dig(config, "access_control", "rules", default=[]) or []
    return render_template(
        "index.html",
        status=authelia_status(),
        version=authelia_version(),
        domain=cookie.get("domain", "not set"),
        portal_url=cookie.get("authelia_url", "not set"),
        theme=config.get("theme", "light"),
        user_count=len(users),
        rule_count=len(rules),
        default_policy=dig(config, "access_control", "default_policy",
                           default="one_factor"),
    )


@app.route("/restart", methods=["POST"])
def restart():
    ok, error = restart_authelia()
    if ok:
        flash("Authelia is restarting. Changes are being applied.", "success")
    else:
        flash(f"Restart failed: {error}", "error")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/validate", methods=["POST"])
def validate():
    ok, output = validate_config_file(CONFIG_PATH)
    if ok:
        flash("Configuration is valid." + (f" {output}" if output else ""),
              "success")
    else:
        flash(f"Configuration has problems: {output}", "error")
    return redirect(request.referrer or url_for("dashboard"))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    config = load_config()
    if request.method == "POST":
        form = request.form
        domain = form.get("domain", "").strip()
        authelia_url = form.get("authelia_url", "").strip()
        if not domain or not authelia_url:
            flash("Domain and portal URL are required.", "error")
            return redirect(url_for("settings"))

        cookie = {
            "domain": domain,
            "authelia_url": authelia_url,
        }
        redirection = form.get("default_redirection_url", "").strip()
        if redirection:
            cookie["default_redirection_url"] = redirection
        config.setdefault("session", {})
        config["session"]["cookies"] = [cookie]
        config["session"]["expiration"] = form.get("expiration", "1h").strip()
        config["session"]["inactivity"] = form.get("inactivity", "5m").strip()
        config["session"]["remember_me"] = form.get("remember_me",
                                                    "1M").strip()

        config.setdefault("log", {})["level"] = form.get("log_level", "info")
        config.setdefault("totp", {})["issuer"] = (
            form.get("totp_issuer", "").strip() or domain)

        config.setdefault("regulation", {})
        try:
            config["regulation"]["max_retries"] = int(
                form.get("max_retries", "3"))
        except ValueError:
            config["regulation"]["max_retries"] = 3
        config["regulation"]["ban_time"] = form.get("ban_time", "5m").strip()
        config["regulation"]["find_time"] = form.get("find_time",
                                                     "2m").strip()

        save_config(config)
        flash("Settings saved. Restart Authelia to apply.", "success")
        return redirect(url_for("settings"))

    cookie = first_cookie(config)
    return render_template(
        "settings.html",
        domain=cookie.get("domain", ""),
        authelia_url=cookie.get("authelia_url", ""),
        default_redirection_url=cookie.get("default_redirection_url", ""),
        expiration=dig(config, "session", "expiration", default="1h"),
        inactivity=dig(config, "session", "inactivity", default="5m"),
        remember_me=dig(config, "session", "remember_me", default="1M"),
        log_level=dig(config, "log", "level", default="info"),
        totp_issuer=dig(config, "totp", "issuer", default=""),
        max_retries=dig(config, "regulation", "max_retries", default=3),
        ban_time=dig(config, "regulation", "ban_time", default="5m"),
        find_time=dig(config, "regulation", "find_time", default="2m"),
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


@app.route("/users")
def users():
    data = load_users()
    return render_template("users.html", users=data["users"])


@app.route("/users/add", methods=["POST"])
def users_add():
    form = request.form
    username = form.get("username", "").strip()
    password = form.get("password", "")
    if not USERNAME_RE.match(username):
        flash("Invalid username (letters, digits, . _ - only).", "error")
        return redirect(url_for("users"))
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("users"))

    data = load_users()
    if username in data["users"]:
        flash(f"User '{username}' already exists.", "error")
        return redirect(url_for("users"))

    try:
        digest = hash_password(password)
    except Exception as exc:  # noqa: BLE001
        flash(f"Password hashing failed: {exc}", "error")
        return redirect(url_for("users"))

    groups = [g.strip() for g in form.get("groups", "").split(",")
              if g.strip()]
    data["users"][username] = {
        "disabled": False,
        "displayname": form.get("displayname", "").strip() or username,
        "email": form.get("email", "").strip(),
        "password": digest,
        "groups": groups,
    }
    save_users(data)
    flash(f"User '{username}' created. Restart Authelia to apply.", "success")
    return redirect(url_for("users"))


@app.route("/users/<username>/password", methods=["POST"])
def users_password(username):
    password = request.form.get("password", "")
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("users"))
    data = load_users()
    if username not in data["users"]:
        flash(f"Unknown user '{username}'.", "error")
        return redirect(url_for("users"))
    try:
        data["users"][username]["password"] = hash_password(password)
    except Exception as exc:  # noqa: BLE001
        flash(f"Password hashing failed: {exc}", "error")
        return redirect(url_for("users"))
    save_users(data)
    flash(f"Password for '{username}' updated. Restart Authelia to apply.",
          "success")
    return redirect(url_for("users"))


@app.route("/users/<username>/toggle", methods=["POST"])
def users_toggle(username):
    data = load_users()
    if username not in data["users"]:
        flash(f"Unknown user '{username}'.", "error")
        return redirect(url_for("users"))
    user = data["users"][username]
    user["disabled"] = not user.get("disabled", False)
    save_users(data)
    state = "disabled" if user["disabled"] else "enabled"
    flash(f"User '{username}' {state}. Restart Authelia to apply.", "success")
    return redirect(url_for("users"))


@app.route("/users/<username>/delete", methods=["POST"])
def users_delete(username):
    data = load_users()
    if username not in data["users"]:
        flash(f"Unknown user '{username}'.", "error")
        return redirect(url_for("users"))
    if len(data["users"]) == 1:
        flash("Refusing to delete the last remaining user.", "error")
        return redirect(url_for("users"))
    del data["users"][username]
    save_users(data)
    flash(f"User '{username}' deleted. Restart Authelia to apply.", "success")
    return redirect(url_for("users"))


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

@app.route("/access")
def access():
    config = load_config()
    rules = dig(config, "access_control", "rules", default=[]) or []
    default_policy = dig(config, "access_control", "default_policy",
                         default="one_factor")
    return render_template("access.html", rules=rules,
                           default_policy=default_policy)


@app.route("/access/default", methods=["POST"])
def access_default():
    policy = request.form.get("default_policy", "one_factor")
    if policy not in POLICIES:
        flash("Invalid policy.", "error")
        return redirect(url_for("access"))
    config = load_config()
    config.setdefault("access_control", {})["default_policy"] = policy
    save_config(config)
    flash("Default policy saved. Restart Authelia to apply.", "success")
    return redirect(url_for("access"))


def _split_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


@app.route("/access/add", methods=["POST"])
def access_add():
    form = request.form
    domains = _split_csv(form.get("domain", ""))
    policy = form.get("policy", "one_factor")
    if not domains:
        flash("At least one domain is required.", "error")
        return redirect(url_for("access"))
    if policy not in POLICIES:
        flash("Invalid policy.", "error")
        return redirect(url_for("access"))

    rule = {"domain": domains, "policy": policy}
    subjects = _split_csv(form.get("subjects", ""))
    if subjects:
        rule["subject"] = subjects
    resources = _split_csv(form.get("resources", ""))
    if resources:
        rule["resources"] = resources

    config = load_config()
    config.setdefault("access_control", {}).setdefault("rules", [])
    if config["access_control"]["rules"] is None:
        config["access_control"]["rules"] = []
    config["access_control"]["rules"].append(rule)
    save_config(config)
    flash("Rule added. Restart Authelia to apply.", "success")
    return redirect(url_for("access"))


@app.route("/access/<int:index>/delete", methods=["POST"])
def access_delete(index):
    config = load_config()
    rules = dig(config, "access_control", "rules", default=[]) or []
    if 0 <= index < len(rules):
        rules.pop(index)
        config["access_control"]["rules"] = rules
        save_config(config)
        flash("Rule deleted. Restart Authelia to apply.", "success")
    else:
        flash("Unknown rule.", "error")
    return redirect(url_for("access"))


@app.route("/access/<int:index>/move", methods=["POST"])
def access_move(index):
    direction = request.form.get("direction")
    config = load_config()
    rules = dig(config, "access_control", "rules", default=[]) or []
    target = index - 1 if direction == "up" else index + 1
    if 0 <= index < len(rules) and 0 <= target < len(rules):
        rules[index], rules[target] = rules[target], rules[index]
        config["access_control"]["rules"] = rules
        save_config(config)
        flash("Rule order updated. Restart Authelia to apply.", "success")
    return redirect(url_for("access"))


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

@app.route("/branding", methods=["GET", "POST"])
def branding():
    config = load_config()
    if request.method == "POST":
        theme = request.form.get("theme", "light")
        if theme not in THEMES:
            flash("Invalid theme.", "error")
            return redirect(url_for("branding"))
        config["theme"] = theme
        config.setdefault("server", {})["asset_path"] = ASSETS_DIR
        save_config(config)

        os.makedirs(ASSETS_DIR, exist_ok=True)
        logo = request.files.get("logo")
        if logo and logo.filename:
            if not logo.filename.lower().endswith(".png"):
                flash("Logo must be a PNG file.", "error")
                return redirect(url_for("branding"))
            logo.save(os.path.join(ASSETS_DIR, "logo.png"))
        favicon = request.files.get("favicon")
        if favicon and favicon.filename:
            if not favicon.filename.lower().endswith(".ico"):
                flash("Favicon must be an ICO file.", "error")
                return redirect(url_for("branding"))
            favicon.save(os.path.join(ASSETS_DIR, "favicon.ico"))

        flash("Branding saved. Restart Authelia to apply.", "success")
        return redirect(url_for("branding"))

    return render_template(
        "branding.html",
        theme=config.get("theme", "light"),
        has_logo=os.path.exists(os.path.join(ASSETS_DIR, "logo.png")),
        has_favicon=os.path.exists(os.path.join(ASSETS_DIR, "favicon.ico")),
    )


@app.route("/branding/reset/<asset>", methods=["POST"])
def branding_reset(asset):
    filename = {"logo": "logo.png", "favicon": "favicon.ico"}.get(asset)
    if not filename:
        flash("Unknown asset.", "error")
        return redirect(url_for("branding"))
    try:
        os.remove(os.path.join(ASSETS_DIR, filename))
        mark_restart_needed()
        flash(f"Custom {asset} removed. Restart Authelia to apply.",
              "success")
    except FileNotFoundError:
        flash(f"No custom {asset} to remove.", "error")
    return redirect(url_for("branding"))


# ---------------------------------------------------------------------------
# Raw YAML editor
# ---------------------------------------------------------------------------

@app.route("/editor", methods=["GET", "POST"])
def editor():
    if request.method == "POST":
        content = request.form.get("content", "")
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as exc:
            flash(f"YAML syntax error: {exc}", "error")
            return render_template("editor.html", content=content)

        tmp_path = "/tmp/authelia_config_candidate.yml"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        ok, output = validate_config_file(tmp_path)
        if not ok:
            flash(f"Authelia rejected the configuration: {output}", "error")
            return render_template("editor.html", content=content)

        if os.path.exists(CONFIG_PATH):
            shutil.copy2(CONFIG_PATH, CONFIG_PATH + ".bak")
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            fh.write(content)
        mark_restart_needed()
        flash("Configuration saved. Restart Authelia to apply.", "success")
        return redirect(url_for("editor"))

    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError:
        content = ""
    return render_template("editor.html", content=content)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
