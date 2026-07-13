"""Admin UI for the Better Authelia Home Assistant addon.

Served through Home Assistant ingress on port 8099. Reads and writes the
Authelia configuration and users database in /config and controls the
Authelia s6 service to apply changes.
"""

import os
import secrets as pysecrets

from flask import Flask, flash, redirect, render_template, request, url_for

import core
from core import (
    CONFIG_PATH,
    LOG_LEVELS,
    POLICIES,
    THEMES,
    authelia_status,
    authelia_version,
    dig,
    first_cookie,
    load_config,
    load_users,
    restart_authelia,
    validate_config_file,
)
import views_access
import views_advanced
import views_branding
import views_oidc
import views_settings
import views_users

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

app.register_blueprint(views_settings.bp)
app.register_blueprint(views_users.bp)
app.register_blueprint(views_access.bp)
app.register_blueprint(views_oidc.bp)
app.register_blueprint(views_branding.bp)
app.register_blueprint(views_advanced.bp)

NAV = [
    ("dashboard", "Overview"),
    ("settings.general", "General"),
    ("settings.session", "Session"),
    ("settings.security", "Security"),
    ("settings.twofactor", "Two-Factor"),
    ("users.index", "Users"),
    ("access.index", "Access"),
    ("oidc.index", "SSO Clients"),
    ("settings.notifications", "Notifications"),
    ("branding.index", "Branding"),
    ("advanced.editor", "Advanced"),
]


@app.context_processor
def inject_globals():
    return {
        "nav": NAV,
        "restart_needed": os.path.exists(core.RESTART_FLAG),
        "themes": THEMES,
        "policies": POLICIES,
        "log_levels": LOG_LEVELS,
    }


@app.route("/")
def dashboard():
    config = load_config()
    users = load_users()["users"]
    cookie = first_cookie(config)
    rules = dig(config, "access_control", "rules", default=[]) or []
    clients = dig(config, "identity_providers", "oidc", "clients",
                  default=[]) or []
    return render_template(
        "index.html",
        status=authelia_status(),
        version=authelia_version(),
        domain=cookie.get("domain", "not set"),
        portal_url=cookie.get("authelia_url", "not set"),
        theme=config.get("theme", "light"),
        user_count=len(users),
        rule_count=len(rules),
        client_count=len(clients),
        oidc_enabled=dig(config, "identity_providers", "oidc") is not None,
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
