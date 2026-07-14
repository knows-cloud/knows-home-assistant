"""Open-Meteo client: current weather, 7-day forecast, ERA5 archive.

Free, no API key. Fair use is 10 000 calls/day with large requests counted pro rata;
the only heavy call here is the one-off 30-year baseline (~156 calls), which is fetched
once and then cached forever, because the 1961-1990 normals never change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from aiohttp import ClientError, ClientSession

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

TIMEOUT_SECONDS = 60


class OpenMeteoError(Exception):
    """Open-Meteo could not be reached or returned an error."""


@dataclass(slots=True)
class DailyForecast:
    """One day of the forecast."""

    day: date
    condition_code: int
    temperature_max: float | None
    temperature_min: float | None
    precipitation: float | None
    precipitation_probability: int | None
    wind_speed: float | None


@dataclass(slots=True)
class WeatherSnapshot:
    """Everything the weather coordinator needs from one forecast request."""

    temperature: float | None
    humidity: int | None
    condition_code: int | None
    wind_speed: float | None
    wind_bearing: float | None
    pressure: float | None
    apparent_temperature: float | None
    forecast: list[DailyForecast] = field(default_factory=list)


@dataclass(slots=True)
class DailySeries:
    """A plain daily series, as returned by the archive endpoints."""

    dates: list[date]
    temperature_mean: list[float | None]
    precipitation: list[float | None]


async def _get(session: ClientSession, url: str, params: dict[str, str]) -> dict:
    try:
        async with session.get(url, params=params, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise OpenMeteoError(f"{url} antwortete mit HTTP {response.status}")
            payload = await response.json()
    except ClientError as err:
        raise OpenMeteoError(f"{url} nicht erreichbar: {err}") from err

    if payload.get("error"):
        raise OpenMeteoError(str(payload.get("reason", "Unbekannter Fehler")))
    return payload


def _parse_dates(raw: list[str]) -> list[date]:
    return [datetime.fromisoformat(value).date() for value in raw]


async def async_fetch_weather(
    session: ClientSession, latitude: float, longitude: float
) -> WeatherSnapshot:
    """Current conditions and the 7-day forecast.

    Recent history deliberately does not come from this endpoint's `past_days` — see
    `async_fetch_recent`.
    """
    payload = await _get(
        session,
        FORECAST_URL,
        {
            "latitude": f"{latitude:.5f}",
            "longitude": f"{longitude:.5f}",
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
                "wind_speed_10m,wind_direction_10m,pressure_msl"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,precipitation_probability_max,wind_speed_10m_max"
            ),
            "forecast_days": "7",
            "timezone": "auto",
        },
    )

    current = payload.get("current", {})
    daily = payload.get("daily", {})
    days = _parse_dates(daily.get("time", []))

    forecast: list[DailyForecast] = []
    for index, day in enumerate(days):

        def at(key: str, _index: int = index):
            values = daily.get(key, [])
            return values[_index] if _index < len(values) else None

        forecast.append(
            DailyForecast(
                day=day,
                condition_code=at("weather_code") or 0,
                temperature_max=at("temperature_2m_max"),
                temperature_min=at("temperature_2m_min"),
                precipitation=at("precipitation_sum"),
                precipitation_probability=at("precipitation_probability_max"),
                wind_speed=at("wind_speed_10m_max"),
            )
        )

    return WeatherSnapshot(
        temperature=current.get("temperature_2m"),
        humidity=current.get("relative_humidity_2m"),
        condition_code=current.get("weather_code"),
        wind_speed=current.get("wind_speed_10m"),
        wind_bearing=current.get("wind_direction_10m"),
        pressure=current.get("pressure_msl"),
        apparent_temperature=current.get("apparent_temperature"),
        forecast=forecast,
    )


async def async_fetch_recent(
    session: ClientSession, latitude: float, longitude: float, days: int
) -> DailySeries:
    """The last `days` days of daily mean temperature and precipitation, up to today.

    Uses the historical-forecast archive rather than the forecast endpoint's `past_days`.
    `past_days` looks like it goes back 92 days but only carries real values for ~67 of
    them and returns null before that — which quietly emptied the 90-day drought window
    while everything still looked fine. This archive covers 150+ days without gaps, and
    is the same model the bias offset is measured against.
    """
    end = datetime.now().date()
    start = end - timedelta(days=days)
    return await _fetch_daily_series(
        session,
        HISTORICAL_FORECAST_URL,
        latitude,
        longitude,
        start.isoformat(),
        end.isoformat(),
    )


async def _fetch_daily_series(
    session: ClientSession,
    url: str,
    latitude: float,
    longitude: float,
    start: str,
    end: str,
) -> DailySeries:
    payload = await _get(
        session,
        url,
        {
            "latitude": f"{latitude:.5f}",
            "longitude": f"{longitude:.5f}",
            "start_date": start,
            "end_date": end,
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "auto",
        },
    )
    daily = payload.get("daily", {})
    return DailySeries(
        dates=_parse_dates(daily.get("time", [])),
        temperature_mean=daily.get("temperature_2m_mean", []),
        precipitation=daily.get("precipitation_sum", []),
    )


async def async_fetch_archive(
    session: ClientSession, latitude: float, longitude: float, start: str, end: str
) -> DailySeries:
    """ERA5 reanalysis — the source of the 1961-1990 normals."""
    return await _fetch_daily_series(session, ARCHIVE_URL, latitude, longitude, start, end)


async def async_fetch_historical_forecast(
    session: ClientSession, latitude: float, longitude: float, start: str, end: str
) -> DailySeries:
    """Archive of the high-resolution forecast model.

    Needed only to measure how far that model sits from ERA5 at this exact spot, so the
    anomaly can be corrected for it.
    """
    return await _fetch_daily_series(
        session, HISTORICAL_FORECAST_URL, latitude, longitude, start, end
    )
