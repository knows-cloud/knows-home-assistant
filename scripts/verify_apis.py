#!/usr/bin/env python3
"""Check the live APIs still answer the way the integration assumes.

Run this when something looks wrong, or before a release. It talks to the real
endpoints — no mocks — and fails loudly if a field the integration depends on has
disappeared or gone null.

    python3 scripts/verify_apis.py
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
HISTORICAL_FORECAST = "https://historical-forecast-api.open-meteo.com/v1/forecast"
GRUVO = (
    "https://services.bgr.de/arcgis/rest/services/grundwasser/gruvo_v109_short"
    "/MapServer/3/query"
)

PLACES = [
    ("Kassel (Mittelgebirge)", 51.3127, 9.4797),
    ("Berlin (Flachland)", 52.5200, 13.4050),
    ("Wien (kein Grundwasser erwartet)", 48.2082, 16.3738),
]

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        failures.append(f"{label} {detail}".strip())


def get(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(full, timeout=60) as response:
        return json.loads(response.read())


def check_forecast(name: str, lat: float, lon: float) -> None:
    print(f"\nOpen-Meteo Forecast — {name}")
    payload = get(
        FORECAST,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "forecast_days": 7,
            "timezone": "auto",
        },
    )
    current = payload.get("current", {})
    daily = payload.get("daily", {})

    check("current.temperature_2m", isinstance(current.get("temperature_2m"), (int, float)))
    check("current.relative_humidity_2m", current.get("relative_humidity_2m") is not None)
    check("current.weather_code", current.get("weather_code") is not None)
    check("7 Vorhersagetage", len(daily.get("time", [])) == 7,
          f"(gefunden: {len(daily.get('time', []))})")
    codes = daily.get("weather_code", [])
    check("weather_code fuer jeden Tag", len(codes) == 7 and all(c is not None for c in codes))


def check_recent(name: str, lat: float, lon: float) -> None:
    """The drought windows live or die on this series being gap-free."""
    print(f"\nOpen-Meteo Historical-Forecast, letzte 120 Tage — {name}")
    end = date.today()
    start = end - timedelta(days=120)
    payload = get(
        HISTORICAL_FORECAST,
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "auto",
        },
    )
    daily = payload.get("daily", {})
    times = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])
    means = daily.get("temperature_2m_mean", [])

    check("Reihe deckt 120 Tage", len(times) >= 120, f"(gefunden: {len(times)})")
    # This is the check that caught the real bug: the forecast endpoint's past_days
    # silently returns null beyond ~67 days back, which emptied the 90-day window.
    check("precipitation_sum LUECKENLOS ueber 90+ Tage",
          len(precip) >= 91 and all(v is not None for v in precip[-91:]),
          f"(NULLs: {sum(1 for v in precip if v is None)})")
    check("Tagesmittel fuer heute vorhanden",
          bool(means) and means[-1] is not None and times[-1] == end.isoformat())


def check_archive(name: str, lat: float, lon: float) -> None:
    print(f"\nOpen-Meteo ERA5 Baseline 1961-1990 — {name}")
    payload = get(
        ARCHIVE,
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": "1961-01-01",
            "end_date": "1961-12-31",
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "auto",
        },
    )
    daily = payload.get("daily", {})
    means = daily.get("temperature_2m_mean", [])
    precip = daily.get("precipitation_sum", [])

    check("ERA5 reicht bis 1961 zurueck", len(daily.get("time", [])) >= 365)
    check("temperature_2m_mean numerisch", bool(means) and all(v is not None for v in means))
    check("precipitation_sum numerisch", bool(precip) and all(v is not None for v in precip))


def check_bias_source(name: str, lat: float, lon: float) -> None:
    print(f"\nOpen-Meteo Historical-Forecast (Bias-Korrektur) — {name}")
    end = date.today() - timedelta(days=7)
    start = end - timedelta(days=365)
    payload = get(
        HISTORICAL_FORECAST,
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_mean",
            "timezone": "auto",
        },
    )
    means = payload.get("daily", {}).get("temperature_2m_mean", [])
    usable = [v for v in means if v is not None]
    check("Hochaufloesendes Modell liefert Tagesmittel", len(usable) > 300,
          f"(gefunden: {len(usable)})")


def check_gruvo(name: str, lat: float, lon: float, expect_stations: bool) -> None:
    print(f"\nBGR GRUVO — {name}")
    span = 0.5
    # outFields=* is mandatory: the columns are fully qualified
    # (grundwasser.DBO.<table>.<field>) and asking by bare name returns HTTP 400.
    payload = get(
        GRUVO,
        {
            "geometry": f"{lon - span},{lat - span},{lon + span},{lat + span}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "outSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "f": "geojson",
        },
    )
    check("Antwort ohne Fehler", "error" not in payload, str(payload.get("error", "")))
    features = payload.get("features", [])

    if not expect_stations:
        check("Keine Messstellen ausserhalb Deutschlands", len(features) == 0,
              f"(gefunden: {len(features)})")
        return

    check("Messstellen gefunden", len(features) > 0)
    if not features:
        return

    props = {k.rsplit(".", 1)[-1]: v for k, v in features[0]["properties"].items()}
    check("well_id vorhanden", bool(props.get("well_id")))
    check("well_name vorhanden", bool(props.get("well_name")))
    check("Geometrie in WGS84", -180 <= features[0]["geometry"]["coordinates"][0] <= 180)

    classes = [
        {k.rsplit(".", 1)[-1]: v for k, v in f["properties"].items()}.get("state_now_c")
        for f in features
    ]
    known = [c for c in classes if c is not None]
    check("state_now_c ausschliesslich im Bereich 1..5", all(1 <= c <= 5 for c in known),
          f"(gesehen: {sorted(set(known))})")
    check("mindestens eine Messstelle mit Einordnung", len(known) > 0)


def main() -> int:
    for name, lat, lon in PLACES:
        is_germany = "Wien" not in name
        check_forecast(name, lat, lon)
        check_recent(name, lat, lon)
        check_gruvo(name, lat, lon, expect_stations=is_germany)

    # The expensive checks only need to run once.
    name, lat, lon = PLACES[0]
    check_archive(name, lat, lon)
    check_bias_source(name, lat, lon)

    print()
    if failures:
        print(f"{len(failures)} Pruefung(en) fehlgeschlagen:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Alle API-Vertraege erfuellt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
