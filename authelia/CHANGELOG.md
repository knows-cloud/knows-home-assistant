# Changelog

## 1.1.0

- Updated Authelia to 4.39.20.

- **New Home Assistant style UI**: Material design with app bar, tabs, cards,
  settings rows, switches and automatic dark mode. Every setting now has a
  plain-language description written for home admins, not Authelia experts.
- **Segmented settings pages**: General, Session, Security (brute-force
  protection, password policy, password reset), Two-Factor (TOTP + WebAuthn),
  Users, Access, SSO Clients, Notifications, Branding, Advanced.
- **OIDC / SSO client management**: enable the OIDC provider with one click
  (signing keys generated automatically) and manage per-app clients (Grafana,
  Immich, Nextcloud, ...) from the UI — secrets are generated, hashed with
  PBKDF2 and shown once. Includes a per-client "legacy claims in ID token"
  compatibility toggle for apps that broke with Authelia 4.39.
- **Portal custom CSS**: restyle the Authelia login/consent/2FA screens from
  the Branding page. An internal nginx proxy injects
  `/config/assets/custom.css` into the portal — changes apply on the next
  page load, no restart needed.
- **Notifications page**: switch between filesystem and SMTP email delivery
  without touching YAML.
- **User editing**: change display name, email and groups of existing users.
- Authelia now listens internally on `127.0.0.1:9092`; nginx serves port
  `9091`. External reverse-proxy setups are unaffected. Note: TLS configured
  under `server.tls` in the Authelia config is not supported behind the
  internal proxy — terminate TLS at your reverse proxy instead.

## 1.0.0

- Initial release
- Authelia 4.39.4 with seeded single-domain configuration on first start
- Admin UI via Home Assistant ingress:
  - Dashboard with live health status and config validation
  - Settings: domain, portal URL, sessions, regulation, TOTP issuer, log level
  - User management with argon2id password hashing
  - Access-control rule editor with ordering
  - Branding: theme, custom logo and favicon uploads
  - Raw YAML editor validated by `authelia validate-config`
  - One-click Authelia restart (s6) to apply changes
- Auto-generated secrets (JWT, session, storage encryption) via env files
- Initial `admin` user with random password logged once
