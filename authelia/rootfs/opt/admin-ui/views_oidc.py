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

# Claims most apps expected before Authelia 4.39 moved them out of the ID
# token; offered as a per-client compatibility toggle.
LEGACY_ID_TOKEN_CLAIMS = ["email", "email_verified", "name",
                          "preferred_username", "groups"]


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
    else:
        client.pop("public", None)
        client["token_endpoint_auth_method"] = "client_secret_basic"
        if not client.get("client_secret"):
            secret = random_token(64)
            try:
                client["client_secret"] = hash_client_secret(secret)
            except Exception as exc:  # noqa: BLE001
                return None, None, f"Could not hash the client secret: {exc}"

    if form.get("legacy_claims"):
        client["claims_policy"] = "legacy"
    else:
        client.pop("claims_policy", None)

    return client, secret, None


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

        client, secret, error = _client_from_form(request.form)
        if error:
            flash(error, "error")
            return redirect(url_for("oidc.new_client"))
        client = {"client_id": client_id, **client}

        clients = _clients(config)
        clients.append(client)
        setpath(config, "identity_providers", "oidc", "clients",
                value=clients)
        _ensure_legacy_policy(config)
        save_config(config)
        if secret:
            flash(secret, "secret")
        flash(f"Client '{client_id}' created. Restart Authelia to apply.",
              "success")
        return redirect(url_for("oidc.index"))

    return render_template("oidc_client.html", client=None,
                           optional_scopes=OPTIONAL_SCOPES,
                           consent_modes=CONSENT_MODES)


@bp.route("/oidc/clients/<client_id>/edit", methods=["GET", "POST"])
def edit_client(client_id):
    config = load_config()
    client = _find_client(config, client_id)
    if client is None:
        flash(f"Unknown client '{client_id}'.", "error")
        return redirect(url_for("oidc.index"))

    if request.method == "POST":
        updated, secret, error = _client_from_form(request.form,
                                                   existing=client)
        if error:
            flash(error, "error")
            return redirect(url_for("oidc.edit_client",
                                    client_id=client_id))
        client.clear()
        client.update(updated)
        _ensure_legacy_policy(config)
        save_config(config)
        if secret:
            flash(secret, "secret")
        flash(f"Client '{client_id}' updated. Restart Authelia to apply.",
              "success")
        return redirect(url_for("oidc.index"))

    return render_template("oidc_client.html", client=client,
                           optional_scopes=OPTIONAL_SCOPES,
                           consent_modes=CONSENT_MODES)


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
    _ensure_legacy_policy(config)
    save_config(config)
    flash(f"Client '{client_id}' deleted. Restart Authelia to apply.",
          "success")
    return redirect(url_for("oidc.index"))
