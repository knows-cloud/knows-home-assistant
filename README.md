# Knows-Cloud's Home Assistant Repository

This repository serves two things at once — add it in both places if you want both.

## Add-ons

Add via **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.

- **[Better Authelia](authelia/)** — Authelia server + ingress admin UI

## Integrations (HACS)

Add via **HACS → ⋮ → Custom repositories**, category *Integration*.

- **[Klima @ Home](custom_components/klima_at_home/)** — pick a place, get entities for local
  weather with a 7-day forecast, how far today's temperature sits above the 1961–1990 normal, a
  drought tracker (dry-day streak, precipitation deficit, SPI), and the official BGR
  classification of the nearest groundwater wells

---

## Klima @ Home

One location in, environmental entities out — for dashboards and automations.

- 🌡️ **Weather** — condition, temperature, humidity, wind and a **7-day forecast** (Open-Meteo, no
  API key)
- 🔥 **How abnormal is today** — deviation from the **1961–1990** WMO climate normal, corrected for
  the bias between the ERA5 grid cell and the site itself
- 🏜️ **Drought tracker** — consecutive dry days, precipitation as a share of the seasonal normal, and
  **SPI** (the WMO's standard drought index) over 30 and 90 days
- 💧 **Groundwater** — the 3 nearest of the BGR's **4,390 monitoring wells**, with the official
  five-class assessment (*sehr niedrig … sehr hoch*), a `kritisch` flag for automations, plus BGR's
  4-week outlook and trend
- 🌍 Weather works anywhere in the world; groundwater is Germany-only and is simply left out
  elsewhere

> **Honest limitation:** groundwater comes as a **classification, not a level in metres**. The BGR
> does not publish numeric levels nationwide, and only 3 of 16 federal states offer raw measurements
> via an API at all. The integration reports the official class rather than inventing a number —
> see [its documentation](custom_components/klima_at_home/README.md).

---

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
