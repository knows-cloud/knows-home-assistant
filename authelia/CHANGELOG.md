# Changelog

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
