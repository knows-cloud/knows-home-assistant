# Knows-Cloud's Home Assistant Add-on Repository

## Add-ons currently available

- **[Better Authelia](authelia/)** — Authelia server + ingress admin UI
- 
## Better Authelia

[Authelia](https://www.authelia.com/) SSO/2FA for Home Assistant, done right: instead of
hand-editing YAML files (as with existing addons), this addon ships a full **admin UI in
the Home Assistant sidebar** for configuring Authelia — settings, users, access-control
rules, branding — plus one-click restarts to apply changes.

### Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   and add this repository URL.
2. Install **Better Authelia** and follow [its documentation](authelia/DOCS.md).

### Highlights

- 🖥️ Modern Home Assistant style UI — every setting explained in plain language, no Authelia or OIDC expertise needed
- 🗂️ Settings segmented by topic: General, Session, Security, Two-Factor, Users, Access, SSO Clients, Notifications, Branding, Advanced
- 🔑 One-click OIDC provider with per-app SSO client management (Grafana, Immich, Nextcloud, …) — secrets generated, hashed and shown once
- 👤 User management with proper argon2id password hashing
- 🚦 Access-control rule editor (bypass / one_factor / two_factor / deny, ordering, subjects, resources)
- 🎨 Personalization: color theme (light/dark/grey/auto), custom logo and favicon — plus **custom CSS injected into the login portal** to fix its readability or restyle it completely
- 📧 Password-reset emails via SMTP configured from the UI
- ✅ Config changes validated with `authelia validate-config` before they land
- 🔁 Restart Authelia from the UI to apply changes — the addon itself keeps running
- 🔐 Secrets auto-generated and kept out of the config file
