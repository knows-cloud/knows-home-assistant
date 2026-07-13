# Better Authelia

Authelia authentication server for Home Assistant with a full admin UI — no more
hand-editing YAML files over SSH.

## What you get

- **Authelia** (single sign-on portal + 2FA) exposed on port `9091` for your reverse proxy.
- **Admin UI** in the Home Assistant sidebar (via ingress, protected by your HA login) with
  settings segmented by topic, each explained in plain language:
  - **General** — domain, portal URL, after-login destination, log level
  - **Session** — sign-in lifetime, inactivity timeout, "remember me" duration
  - **Security** — brute-force protection, password policy, self-service password reset
  - **Two-Factor** — TOTP (issuer, algorithm, digits, period) and WebAuthn/passkeys
  - **Users** — create, edit, delete, enable/disable, reset passwords (argon2id hashed for you)
  - **Access** — per-domain policies (`bypass` / `one_factor` / `two_factor` / `deny`), subjects and resource regexes, with ordering
  - **SSO Clients** — enable the OIDC provider with one click and manage per-app clients (Grafana, Immich, Nextcloud, …); secrets are generated and hashed for you
  - **Notifications** — filesystem or SMTP email delivery for password-reset links
  - **Branding** — color theme (light/dark/grey/auto), custom portal logo and favicon, and **custom CSS injected into the login portal**
  - **Advanced** — a raw YAML editor for everything else (LDAP, Redis, external DBs…), validated with `authelia validate-config` before saving
  - One-click **Restart Authelia** to apply changes — no addon restart needed

## Installation

1. Add this repository to the Home Assistant add-on store
   (Settings → Add-ons → Add-on Store → ⋮ → Repositories).
2. Install **Better Authelia**.
3. Set the `domain` option to your root domain (e.g. `example.com`) and start the addon.
4. Check the addon log: an initial `admin` user is created with a **randomly generated
   password printed once in the log**. Change it right away in the admin UI.
5. Open **Authelia** from the sidebar to configure everything else.

## First-run defaults

On first start the addon creates in `/addon_configs/xxx_better_authelia/`:

- `configuration.yml` — a working single-domain configuration (file auth backend,
  SQLite storage, filesystem notifier)
- `users_database.yml` — the initial `admin` user
- `secrets/` — randomly generated JWT, session and storage-encryption secrets
  (injected as environment variables, never stored in the config file)
- `assets/` — branding overrides (logo/favicon) live here

Existing files are never overwritten, so upgrading from a manual setup is safe:
drop your own `configuration.yml` in place before first start if you have one.

## Reverse proxy integration

Authelia itself listens on **port 9091**. Point your reverse proxy at it and configure
forward-auth as usual, e.g. for Nginx Proxy Manager / Traefik / Caddy following the
[Authelia proxy integration docs](https://www.authelia.com/integration/proxies/introduction/).
The portal URL you set under *Settings* (e.g. `https://auth.example.com`) must route to
this addon's port 9091.

## Single sign-on for your apps (OIDC)

Open **SSO Clients** and press *Enable OIDC provider* — the addon generates the
signing keys automatically. Then add one client per app. For each client the UI
generates a client secret, hashes it into the configuration and shows the
plaintext **once** — paste it into the app immediately. The page also lists the
issuer/authorization/token/userinfo URLs apps ask for.

If an app logs in fine but doesn't know who the user is (no name/email/roles),
enable the client's **"Include profile details in the ID token"** compatibility
toggle — Authelia 4.39 moved those claims to the userinfo endpoint and some
apps never call it.

## Restyling the login portal

Authelia natively supports only theme, logo and favicon. This addon goes
further: a small internal nginx proxy sits in front of the portal and injects
`/config/assets/custom.css` into every portal page. Edit the CSS on the
**Branding** page — changes apply on the next page load, no restart. If you
break something, clear the field and save.

Because of this proxy, Authelia itself listens on `127.0.0.1:9092` inside the
container while port `9091` is served by nginx. Your reverse proxy setup does
not change. One limitation: configuring TLS under `server.tls` in the Authelia
config is not supported — terminate TLS at your reverse proxy.

## Notes on the notifier

The default configuration uses the **filesystem notifier**: password-reset and identity
verification links are written to `/addon_configs/…/notification.txt` instead of being
emailed. For real email delivery, configure an SMTP notifier in the YAML editor.

## Addon options

| Option | Description |
| ------ | ----------- |
| `domain` | Root domain used to seed the initial configuration (first start only) |
| `log_level` | Log level used to seed the initial configuration (first start only) |

After first start, manage everything through the admin UI — the options above are not
re-applied to an existing configuration.

## Backups & recovery

Every save from the UI keeps the previous version as `configuration.yml.bak` /
`users_database.yml.bak`. The addon config directory is included in Home Assistant
backups.
