"""OpenID Connect provider management: enable the provider and manage the
per-application clients (Grafana, Immich, Nextcloud, ...)."""

import re

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import (
    dig,
    first_cookie,
    generate_rsa_key,
    hash_client_secret,
    load_config,
    random_token,
    save_config,
    setpath,
    split_lines,
)

bp = Blueprint("oidc", __name__)

CLIENT_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
OPTIONAL_SCOPES = ["profile", "email", "groups", "offline_access"]
CONSENT_MODES = ["auto", "explicit", "implicit", "pre-configured"]

# client_secret_jwt needs the secret stored in plaintext and private_key_jwt
# a per-client JWKS; this UI only stores hashed secrets, so both are left out.
CONFIDENTIAL_AUTH_METHODS = ["client_secret_basic", "client_secret_post"]

# Claims most apps expected before Authelia 4.39 moved them out of the ID
# token; offered as a per-client compatibility toggle.
LEGACY_ID_TOKEN_CLAIMS = ["email", "email_verified", "name",
                          "preferred_username", "groups"]

# Authelia duration strings such as "90m", "30d" or "1d12h".
DURATION_RE = re.compile(r"^(\d+\s*(ms|s|m|h|d|w|M|y)\s*)+$")


def _oidc(config):
    return dig(config, "identity_providers", "oidc")


def _clients(config):
    clients = dig(config, "identity_providers", "oidc", "clients", default=[])
    return clients if isinstance(clients, list) else []


def _find_client(config, client_id):
    for client in _clients(config):
        if isinstance(client, dict) and client.get("client_id") == client_id:
            return client
    return None


def _issuer(config):
    return first_cookie(config).get("authelia_url", "").rstrip("/")


@bp.route("/oidc")
def index():
    config = load_config()
    return render_template(
        "oidc.html",
        enabled=_oidc(config) is not None,
        clients=_clients(config),
        issuer=_issuer(config),
    )


@bp.route("/oidc/enable", methods=["POST"])
def enable():
    config = load_config()
    if _oidc(config) is not None:
        flash("OIDC is already enabled.", "error")
        return redirect(url_for("oidc.index"))
    try:
        key = generate_rsa_key()
        hmac = random_token(64)
    except Exception as exc:  # noqa: BLE001
        flash(f"Could not generate keys: {exc}", "error")
        return redirect(url_for("oidc.index"))
    setpath(config, "identity_providers", "oidc", value={
        "hmac_secret": hmac,
        "jwks": [{"key": key}],
        "clients": [],
    })
    save_config(config)
    flash("OIDC provider enabled. Signing keys were generated automatically. "
          "Now add a client for each application.", "success")
    return redirect(url_for("oidc.index"))


def _client_from_form(form, existing=None):
    """Build/refresh a client dict from the submitted form.

    Returns (client, plaintext_secret_or_None, error_or_None).
    """
    client = dict(existing or {})

    name = form.get("client_name", "").strip()
    if name:
        client["client_name"] = name

    redirect_uris = split_lines(form.get("redirect_uris", ""))
    if not redirect_uris:
        return None, None, "At least one redirect URI is required."
    client["redirect_uris"] = redirect_uris

    scopes = ["openid"] + [s for s in OPTIONAL_SCOPES if form.get(f"scope_{s}")]
    client["scopes"] = scopes

    # The UI only sets up the authorization code flow. offline_access is only
    # valid with it and needs the refresh_token grant to be of any use.
    client["response_types"] = ["code"]
    client["grant_types"] = ["authorization_code"] + (
        ["refresh_token"] if "offline_access" in scopes else [])

    policy = form.get("authorization_policy", "one_factor")
    if policy in ("one_factor", "two_factor"):
        client["authorization_policy"] = policy

    consent = form.get("consent_mode", "auto")
    if consent in CONSENT_MODES:
        client["consent_mode"] = consent
        if consent == "pre-configured":
            client["pre_configured_consent_duration"] = (
                form.get("consent_duration", "").strip() or "1M")
        else:
            client.pop("pre_configured_consent_duration", None)

    secret = None
    if form.get("public"):
        client["public"] = True
        client["token_endpoint_auth_method"] = "none"
        client.pop("client_secret", None)
        # Without a secret, PKCE is the only thing protecting the code.
        require_pkce = True
    else:
        client.pop("public", None)
        auth_method = form.get("token_endpoint_auth_method", "")
        client["token_endpoint_auth_method"] = (
            auth_method if auth_method in CONFIDENTIAL_AUTH_METHODS
            else "client_secret_basic")
        if not client.get("client_secret"):
            secret = random_token(64)
            try:
                client["client_secret"] = hash_client_secret(secret)
            except Exception as exc:  # noqa: BLE001
                return None, None, f"Could not hash the client secret: {exc}"
        require_pkce = bool(form.get("require_pkce"))

    if require_pkce:
        client["require_pkce"] = True
        client["pkce_challenge_method"] = "S256"
    else:
        client.pop("require_pkce", None)
        client.pop("pkce_challenge_method", None)

    if form.get("legacy_claims"):
        client["claims_policy"] = "legacy"
    else:
        client.pop("claims_policy", None)

    return client, secret, None


def _custom_lifespans(config):
    custom = dig(config, "identity_providers", "oidc", "lifespans", "custom")
    return custom if isinstance(custom, dict) else {}


def _refresh_lifespan(config, client):
    """The refresh token lifespan of the client's named custom lifespan, or ''."""
    entry = _custom_lifespans(config).get(client.get("lifespan") or "")
    if isinstance(entry, dict):
        return str(entry.get("refresh_token", "") or "")
    return ""


def _drop_empty_lifespans(config):
    oidc = _oidc(config) or {}
    lifespans = oidc.get("lifespans")
    if not isinstance(lifespans, dict):
        return
    if isinstance(lifespans.get("custom"), dict) and not lifespans["custom"]:
        lifespans.pop("custom")
    if not lifespans:
        oidc.pop("lifespans")


def _apply_refresh_lifespan(config, client, value):
    """Store *value* as the refresh token lifespan of *client*.

    Authelia only applies per-client lifespans through a named entry under
    ``lifespans.custom`` that the client references with ``lifespan``. The UI
    names that entry after the client. Other keys someone added to the entry
    in the raw editor are kept; an entry shared with another client is copied
    first so changing one client never changes another.
    """
    client_id = client["client_id"]
    name = client.get("lifespan") or client_id
    custom = _custom_lifespans(config)
    entry = custom.get(name)
    entry = dict(entry) if isinstance(entry, dict) else {}
    shared = any(isinstance(c, dict) and c is not client
                 and c.get("lifespan") == name for c in _clients(config))
    if shared:
        name = client_id

    if value:
        entry["refresh_token"] = value
    else:
        entry.pop("refresh_token", None)

    if entry:
        custom[name] = entry
        setpath(config, "identity_providers", "oidc", "lifespans", "custom",
                value=custom)
        client["lifespan"] = name
    else:
        if not shared:
            custom.pop(name, None)
        client.pop("lifespan", None)
    _drop_empty_lifespans(config)


def _forget_lifespan(config, client_id):
    """Drop the custom lifespan named after a deleted client if unused."""
    if any(isinstance(c, dict) and c.get("lifespan") == client_id
           for c in _clients(config)):
        return
    _custom_lifespans(config).pop(client_id, None)
    _drop_empty_lifespans(config)


def _lifespan_from_form(form):
    """Returns (value, error_or_None)."""
    value = form.get("refresh_token_lifespan", "").strip()
    if value and not DURATION_RE.match(value):
        return None, ("Invalid duration for “Stay signed in for”. Use a "
                      "number with a unit, e.g. 90m, 12h, 7d or 1M.")
    return value, None


def _ensure_legacy_policy(config):
    clients = _clients(config)
    uses_legacy = any(c.get("claims_policy") == "legacy" for c in clients
                      if isinstance(c, dict))
    if uses_legacy:
        setpath(config, "identity_providers", "oidc", "claims_policies",
                "legacy", "id_token", value=list(LEGACY_ID_TOKEN_CLAIMS))
    else:
        oidc = _oidc(config) or {}
        policies = oidc.get("claims_policies")
        if isinstance(policies, dict):
            policies.pop("legacy", None)
            if not policies:
                oidc.pop("claims_policies", None)


@bp.route("/oidc/clients/new", methods=["GET", "POST"])
def new_client():
    config = load_config()
    if _oidc(config) is None:
        flash("Enable the OIDC provider first.", "error")
        return redirect(url_for("oidc.index"))

    if request.method == "POST":
        client_id = request.form.get("client_id", "").strip()
        if not CLIENT_ID_RE.match(client_id):
            flash("Invalid client ID (letters, digits, . _ - only).", "error")
            return redirect(url_for("oidc.new_client"))
        if _find_client(config, client_id):
            flash(f"A client named '{client_id}' already exists.", "error")
            return redirect(url_for("oidc.new_client"))

        lifespan, error = _lifespan_from_form(request.form)
        if not error:
            client, secret, error = _client_from_form(request.form)
        if error:
            flash(error, "error")
            return redirect(url_for("oidc.new_client"))
        client = {"client_id": client_id, **client}

        clients = _clients(config)
        clients.append(client)
        setpath(config, "identity_providers", "oidc", "clients",
                value=clients)
        _apply_refresh_lifespan(config, client, lifespan)
        _ensure_legacy_policy(config)
        save_config(config)
        if secret:
            flash(secret, "secret")
        flash(f"Client '{client_id}' created. Restart Authelia to apply.",
              "success")
        return redirect(url_for("oidc.index"))

    return render_template("oidc_client.html", client=None,
                           refresh_lifespan="",
                           optional_scopes=OPTIONAL_SCOPES,
                           consent_modes=CONSENT_MODES,
                           auth_methods=CONFIDENTIAL_AUTH_METHODS)


@bp.route("/oidc/clients/<client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    config = load_config()
    client = _find_client(config, client_id)
    if client is None:
        flash(f"Unknown client '{client_id}'.", "error")
        return redirect(url_for("oidc.index"))

    if request.method == "POST":
        lifespan, error = _lifespan_from_form(request.form)
        if not error:
            updated, secret, error = _client_from_form(request.form,
                                                       existing=client)
        if error:
            flash(error, "error")
            return redirect(url_for("oidc.edit_client",
                                    client_id=client_id))
        client.clear()
        client.update(updated)
        _apply_refresh_lifespan(config, client, lifespan)
        _ensure_legacy_policy(config)
        save_config(config)
        if secret:
            flash(secret, "secret")
        flash(f"Client '{client_id}' updated. Restart Authelia to apply.",
              "success")
        return redirect(url_for("oidc.index"))

    return render_template("oidc_client.html", client=client,
                           refresh_lifespan=_refresh_lifespan(config, client),
                           optional_scopes=OPTIONAL_SCOPES,
                           consent_modes=CONSENT_MODES,
                           auth_methods=CONFIDENTIAL_AUTH_METHODS)


@bp.route("/oidc/clients/<client_id>/secret", methods=["POST"])
def regenerate_secret(client_id):
    config = load_config()
    client = _find_client(config, client_id)
    if client is None:
        flash(f"Unknown client '{client_id}'.", "error")
        return redirect(url_for("oidc.index"))
    if client.get("public"):
        flash("Public clients do not use a secret.", "error")
        return redirect(url_for("oidc.index"))
    try:
        secret = random_token(64)
        client["client_secret"] = hash_client_secret(secret)
    except Exception as exc:  # noqa: BLE001
        flash(f"Could not generate a new secret: {exc}", "error")
        return redirect(url_for("oidc.index"))
    save_config(config)
    flash(secret, "secret")
    flash(f"New secret for '{client_id}' generated. Update the application "
          "with it, then restart Authelia.", "success")
    return redirect(url_for("oidc.index"))


@bp.route("/oidc/clients/<client_id>/delete", methods=["POST"])
def delete_client(client_id):
    config = load_config()
    clients = _clients(config)
    remaining = [c for c in clients
                 if not (isinstance(c, dict)
                         and c.get("client_id") == client_id)]
    if len(remaining) == len(clients):
        flash(f"Unknown client '{client_id}'.", "error")
        return redirect(url_for("oidc.index"))
    setpath(config, "identity_providers", "oidc", "clients", value=remaining)
    _forget_lifespan(config, client_id)
    _ensure_legacy_policy(config)
    save_config(config)
    flash(f"Client '{client_id}' deleted. Restart Authelia to apply.",
          "success")
    return redirect(url_for("oidc.index"))
