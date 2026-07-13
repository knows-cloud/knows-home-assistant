"""Segmented settings pages: General, Session, Security, Two-Factor,
Notifications."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import (
    LOG_LEVELS,
    dig,
    droppath,
    first_cookie,
    load_config,
    save_config,
    setpath,
)

bp = Blueprint("settings", __name__)


def _duration(form, field, default):
    value = form.get(field, "").strip()
    return value or default


def _int(form, field, default):
    try:
        return int(form.get(field, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------

@bp.route("/general", methods=["GET", "POST"])
def general():
    config = load_config()
    if request.method == "POST":
        form = request.form
        domain = form.get("domain", "").strip()
        authelia_url = form.get("authelia_url", "").strip()
        if not domain or not authelia_url:
            flash("Domain and portal URL are required.", "error")
            return redirect(url_for("settings.general"))

        cookie = dict(first_cookie(config))
        cookie["domain"] = domain
        cookie["authelia_url"] = authelia_url
        redirection = form.get("default_redirection_url", "").strip()
        if redirection:
            cookie["default_redirection_url"] = redirection
        else:
            cookie.pop("default_redirection_url", None)
        setpath(config, "session", "cookies", value=[cookie])

        level = form.get("log_level", "info")
        if level in LOG_LEVELS:
            setpath(config, "log", "level", value=level)

        save_config(config)
        flash("General settings saved.", "success")
        return redirect(url_for("settings.general"))

    cookie = first_cookie(config)
    return render_template(
        "general.html",
        domain=cookie.get("domain", ""),
        authelia_url=cookie.get("authelia_url", ""),
        default_redirection_url=cookie.get("default_redirection_url", ""),
        log_level=dig(config, "log", "level", default="info"),
    )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

@bp.route("/session", methods=["GET", "POST"])
def session():
    config = load_config()
    if request.method == "POST":
        form = request.form
        setpath(config, "session", "expiration",
                value=_duration(form, "expiration", "1h"))
        setpath(config, "session", "inactivity",
                value=_duration(form, "inactivity", "5m"))
        setpath(config, "session", "remember_me",
                value=_duration(form, "remember_me", "1M"))
        save_config(config)
        flash("Session settings saved.", "success")
        return redirect(url_for("settings.session"))

    return render_template(
        "session.html",
        expiration=dig(config, "session", "expiration", default="1h"),
        inactivity=dig(config, "session", "inactivity", default="5m"),
        remember_me=dig(config, "session", "remember_me", default="1M"),
    )


# ---------------------------------------------------------------------------
# Security (brute-force protection + password policy)
# ---------------------------------------------------------------------------

@bp.route("/security", methods=["GET", "POST"])
def security():
    config = load_config()
    if request.method == "POST":
        form = request.form
        setpath(config, "regulation", "max_retries",
                value=_int(form, "max_retries", 3))
        setpath(config, "regulation", "find_time",
                value=_duration(form, "find_time", "2m"))
        setpath(config, "regulation", "ban_time",
                value=_duration(form, "ban_time", "5m"))

        if form.get("policy_enabled"):
            policy = {
                "enabled": True,
                "min_length": _int(form, "min_length", 8),
                "require_uppercase": bool(form.get("require_uppercase")),
                "require_lowercase": bool(form.get("require_lowercase")),
                "require_number": bool(form.get("require_number")),
                "require_special": bool(form.get("require_special")),
            }
            setpath(config, "password_policy", "standard", value=policy)
        else:
            droppath(config, "password_policy", "standard")
            if not dig(config, "password_policy"):
                config.pop("password_policy", None)

        if form.get("allow_reset"):
            droppath(config, "authentication_backend", "password_reset")
        else:
            setpath(config, "authentication_backend", "password_reset",
                    "disable", value=True)

        save_config(config)
        flash("Security settings saved.", "success")
        return redirect(url_for("settings.security"))

    return render_template(
        "security.html",
        max_retries=dig(config, "regulation", "max_retries", default=3),
        find_time=dig(config, "regulation", "find_time", default="2m"),
        ban_time=dig(config, "regulation", "ban_time", default="5m"),
        policy_enabled=dig(config, "password_policy", "standard", "enabled",
                           default=False),
        min_length=dig(config, "password_policy", "standard", "min_length",
                       default=8),
        require_uppercase=dig(config, "password_policy", "standard",
                              "require_uppercase", default=False),
        require_lowercase=dig(config, "password_policy", "standard",
                              "require_lowercase", default=False),
        require_number=dig(config, "password_policy", "standard",
                           "require_number", default=False),
        require_special=dig(config, "password_policy", "standard",
                            "require_special", default=False),
        allow_reset=not dig(config, "authentication_backend",
                            "password_reset", "disable", default=False),
    )


# ---------------------------------------------------------------------------
# Two-factor (TOTP + WebAuthn)
# ---------------------------------------------------------------------------

TOTP_ALGORITHMS = ["SHA1", "SHA256", "SHA512"]
WEBAUTHN_VERIFICATION = ["preferred", "required", "discouraged"]


@bp.route("/twofactor", methods=["GET", "POST"])
def twofactor():
    config = load_config()
    if request.method == "POST":
        form = request.form

        setpath(config, "totp", "disable",
                value=not bool(form.get("totp_enabled")))
        issuer = form.get("totp_issuer", "").strip()
        if issuer:
            setpath(config, "totp", "issuer", value=issuer)
        algorithm = form.get("totp_algorithm", "SHA1")
        if algorithm in TOTP_ALGORITHMS:
            setpath(config, "totp", "algorithm", value=algorithm)
        digits = _int(form, "totp_digits", 6)
        setpath(config, "totp", "digits", value=digits if digits in (6, 8)
                else 6)
        setpath(config, "totp", "period",
                value=max(15, _int(form, "totp_period", 30)))

        setpath(config, "webauthn", "disable",
                value=not bool(form.get("webauthn_enabled")))
        display_name = form.get("webauthn_display_name", "").strip()
        if display_name:
            setpath(config, "webauthn", "display_name", value=display_name)
        verification = form.get("webauthn_user_verification", "preferred")
        if verification in WEBAUTHN_VERIFICATION:
            setpath(config, "webauthn", "selection_criteria",
                    "user_verification", value=verification)

        save_config(config)
        flash("Two-factor settings saved.", "success")
        return redirect(url_for("settings.twofactor"))

    return render_template(
        "twofactor.html",
        totp_enabled=not dig(config, "totp", "disable", default=False),
        totp_issuer=dig(config, "totp", "issuer", default=""),
        totp_algorithm=dig(config, "totp", "algorithm", default="SHA1"),
        totp_digits=dig(config, "totp", "digits", default=6),
        totp_period=dig(config, "totp", "period", default=30),
        totp_algorithms=TOTP_ALGORITHMS,
        webauthn_enabled=not dig(config, "webauthn", "disable",
                                 default=False),
        webauthn_display_name=dig(config, "webauthn", "display_name",
                                  default=""),
        webauthn_user_verification=dig(config, "webauthn",
                                       "selection_criteria",
                                       "user_verification",
                                       default="preferred"),
        webauthn_verifications=WEBAUTHN_VERIFICATION,
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@bp.route("/notifications", methods=["GET", "POST"])
def notifications():
    config = load_config()
    if request.method == "POST":
        form = request.form
        mode = form.get("mode", "filesystem")
        if mode == "smtp":
            host = form.get("smtp_host", "").strip()
            sender = form.get("smtp_sender", "").strip()
            if not host or not sender:
                flash("SMTP server and sender address are required.", "error")
                return redirect(url_for("settings.notifications"))
            port = _int(form, "smtp_port", 587)
            smtp = {
                "address": f"submission://{host}:{port}",
                "sender": sender,
            }
            username = form.get("smtp_username", "").strip()
            if username:
                smtp["username"] = username
            password = form.get("smtp_password", "")
            existing = dig(config, "notifier", "smtp", "password")
            if password:
                smtp["password"] = password
            elif existing:
                smtp["password"] = existing
            if form.get("disable_require_tls"):
                smtp["disable_require_tls"] = True
            config["notifier"] = {"smtp": smtp}
        else:
            config["notifier"] = {
                "filesystem": {"filename": "/config/notification.txt"},
            }
        save_config(config)
        flash("Notification settings saved.", "success")
        return redirect(url_for("settings.notifications"))

    smtp = dig(config, "notifier", "smtp", default={}) or {}
    address = smtp.get("address", "")
    host, port = "", 587
    match = address
    if "://" in match:
        match = match.split("://", 1)[1]
    if match:
        if ":" in match:
            host, _, port_s = match.rpartition(":")
            try:
                port = int(port_s)
            except ValueError:
                host = match
        else:
            host = match
    return render_template(
        "notifications.html",
        mode="smtp" if smtp else "filesystem",
        smtp_host=host,
        smtp_port=port,
        smtp_sender=smtp.get("sender", ""),
        smtp_username=smtp.get("username", ""),
        has_password=bool(smtp.get("password")),
        disable_require_tls=smtp.get("disable_require_tls", False),
    )
