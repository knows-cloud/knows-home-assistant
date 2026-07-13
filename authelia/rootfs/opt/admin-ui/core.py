"""Shared helpers for the Better Authelia admin UI.

All configuration IO, Authelia CLI wrappers and service control live here so
the view modules stay small.
"""

import json
import os
import re
import shutil
import subprocess
import urllib.request

import yaml

CONFIG_PATH = os.environ.get("AUTHELIA_CONFIG", "/config/configuration.yml")
USERS_PATH = os.environ.get("AUTHELIA_USERS", "/config/users_database.yml")
ASSETS_DIR = os.environ.get("AUTHELIA_ASSETS", "/config/assets")
SECRETS_DIR = os.environ.get("AUTHELIA_SECRETS", "/config/secrets")
CUSTOM_CSS = os.path.join(ASSETS_DIR, "custom.css")
RESTART_FLAG = "/tmp/authelia_restart_needed"
SERVICE_DIR = "/run/service/authelia"
HEALTH_URL = "http://127.0.0.1:9091/api/health"

THEMES = ["light", "dark", "grey", "auto"]
POLICIES = ["bypass", "one_factor", "two_factor", "deny"]
LOG_LEVELS = ["trace", "debug", "info", "warn", "error"]

# Render multi-line strings (PEM keys) as YAML literal blocks so the config
# file stays readable and Authelia can parse them.


class _ConfigDumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper, value):
    if "\n" in value:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value,
                                       style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


_ConfigDumper.add_representer(str, _str_presenter)


# ---------------------------------------------------------------------------
# Config / users IO
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
        yaml.dump(config, fh, Dumper=_ConfigDumper, default_flow_style=False,
                  sort_keys=False, allow_unicode=True)
    # The config may hold inline secrets (OIDC keys, SMTP password).
    os.chmod(CONFIG_PATH, 0o600)
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


def setpath(config, *keys, value):
    node = config
    for key in keys[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    node[keys[-1]] = value


def droppath(config, *keys):
    node = config
    for key in keys[:-1]:
        node = node.get(key)
        if not isinstance(node, dict):
            return
    node.pop(keys[-1], None)


def first_cookie(config):
    cookies = dig(config, "session", "cookies", default=None)
    if isinstance(cookies, list) and cookies and isinstance(cookies[0], dict):
        return cookies[0]
    return {}


def split_csv(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def split_lines(value):
    return [line.strip() for line in value.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Authelia CLI wrappers
# ---------------------------------------------------------------------------

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


def hash_client_secret(secret):
    """Hash an OIDC client secret with PBKDF2 (broadly compatible)."""
    proc = subprocess.run(
        ["authelia", "crypto", "hash", "generate", "pbkdf2",
         "--variant", "sha512", "--password", secret],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "hashing failed")
    match = re.search(r"Digest:\s*(\S+)", proc.stdout)
    if not match:
        raise RuntimeError("could not parse secret digest")
    return match.group(1)


def generate_rsa_key():
    """Return a PEM encoded RSA 2048 private key for OIDC token signing."""
    proc = subprocess.run(["openssl", "genrsa", "2048"],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0 or "PRIVATE KEY" not in proc.stdout:
        raise RuntimeError(proc.stderr.strip() or "key generation failed")
    return proc.stdout


def random_token(length=64):
    proc = subprocess.run(["openssl", "rand", "-hex", str(length // 2)],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError("random generation failed")
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Service control / status
# ---------------------------------------------------------------------------

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
