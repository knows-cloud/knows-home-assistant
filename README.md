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

### Setup

**Settings → Devices & Services → Add Integration → Klima @ Home**, then pick the location on the
map (your home is pre-filled). Nothing else to configure.

The **first** start downloads 30 years of climate data (1961–1990) for that spot, which takes a
moment. It happens exactly once and is then cached — restarts do not trigger it again.

### What the entities mean

Every number below answers a *different* question, which is why there are several of them.

| Entity | Example | What it actually says |
|---|---|---|
| **Weather** | `partlycloudy`, 23.7 °C | Condition, temperature, humidity, wind + **7-day forecast** |
| **Temperature anomaly** | **+5.3 °C** | How far *today* sits above the long-term mean **of the same calendar day**, 1961–1990. Not "warmer than yesterday". |
| **Days without rain** | **15 d** | Length of the current dry spell. A **dry day is < 1 mm** (ETCCDI) — not 0 mm, or a single drizzle reading would reset the streak. |
| **Precipitation 30 d / 90 d** | **45 % / 74 %** | Rainfall as a **share of what is normal for this season**. 100 % = an ordinary month. 30 d is topsoil and lawns; 90 d is trees and groundwater recharge. |
| **SPI 30 d / 90 d** | **−1.47** → *moderate drought* | How **unusual** that rainfall is here, in standard deviations — the WMO's standard drought index. Percentages tell you *how much*; SPI tells you whether it is *exceptional*. |
| **Drought** (binary) | **Problem** | Home Assistant labels `problem` sensors "Problem"/"OK" — **"Problem" simply means: drought right now.** |
| **Groundwater classification** ×3 | `niedrig` | The BGR's official class for the nearest wells (percentiles vs. 1991–2020). |
| **Groundwater critical** (binary) | **Problem** | On when the BGR classes that well as *sehr niedrig*. |

**Why drought can be on although it rained yesterday.** Two independent criteria fire it, because
they catch different things: **≥ 14 days without rain** (what people notice) or **SPI-30 ≤ −1.0**, a
genuine rainfall deficit (what plants and groundwater notice). A month of occasional drizzle far
below normal *is* a drought, even with "days without rain" at 0. The `ausgeloest_durch` attribute
names the criterion that actually fired.

**SPI scale:** ≤ −2.0 extreme drought · −2.0…−1.5 severe · −1.5…−1.0 moderate · −1.0…+1.0 normal ·
above that, wet. The `einordnung` attribute spells this out on the entity itself.

> **Honest limitation:** groundwater comes as a **classification, not a level in metres**. The BGR
> does not publish numeric levels nationwide, and only 3 of 16 federal states offer raw measurements
> via an API at all. The integration reports the official class rather than inventing a number.

📖 **[Full documentation (German)](https://github.com/knows-cloud/knows-home-assistant/blob/main/custom_components/klima_at_home/README.md)** — the methodology behind every number, the
groundwater data situation in detail, and example automations.

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
