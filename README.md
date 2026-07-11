# Better Authelia — Home Assistant Add-on Repository

[Authelia](https://www.authelia.com/) SSO/2FA for Home Assistant, done right: instead of
hand-editing YAML files (as with existing addons), this addon ships a full **admin UI in
the Home Assistant sidebar** for configuring Authelia — settings, users, access-control
rules, branding — plus one-click restarts to apply changes.

## Add-ons

- **[Better Authelia](authelia/)** — Authelia server + ingress admin UI

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   and add this repository URL.
2. Install **Better Authelia** and follow [its documentation](authelia/DOCS.md).

## Highlights

- 🖥️ Real configuration UI (no SSH, no YAML required for common tasks)
- 👤 User management with proper argon2id password hashing
- 🚦 Access-control rule editor (bypass / one_factor / two_factor / deny, ordering, subjects, resources)
- 🎨 Personalization: color theme (light/dark/grey/auto), custom logo and favicon for the SSO portal
- ✅ Config changes validated with `authelia validate-config` before they land
- 🔁 Restart Authelia from the UI to apply changes — the addon itself keeps running
- 🔐 Secrets auto-generated and kept out of the config file
