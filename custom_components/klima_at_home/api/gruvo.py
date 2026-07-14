"""BGR GRUVO client — nationwide groundwater classification.

GRUVO covers ~4 390 monitoring wells across Germany and publishes, per well, the
official five-class assessment of the current groundwater level (percentiles against the
1991-2020 reference period), plus a 4- and 12-week forecast and a trend bucket.

It does NOT publish a numeric level in metres through this service. That is a property
of the source, not an omission here: of the 16 federal states only three offer automated
access to raw measurements at all. The integration therefore reports the official class
and says nothing about metres, rather than inventing a number.

Endpoint quirk worth knowing: the layer's fields are fully qualified
(`grundwasser.DBO.<table>.<field>`), and asking for them by bare name returns HTTP 400.
`outFields=*` is the only thing that works, so the response is unpacked by field suffix.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

from aiohttp import ClientError, ClientSession

# Layer 3 = "Clustermessstellen" — every well, with state_now_* attached.
# Layer 2 holds only the ~120 reference wells.
QUERY_URL = (
    "https://services.bgr.de/arcgis/rest/services/grundwasser/gruvo_v109_short"
    "/MapServer/3/query"
)

TIMEOUT_SECONDS = 45

# Widen the search until enough wells turn up. Most of Germany is covered densely
# enough that the first step suffices; the last step is for the sparse corners.
SEARCH_RADII_KM = (25.0, 50.0, 100.0, 200.0)

EARTH_RADIUS_KM = 6371.0


class GruvoError(Exception):
    """GRUVO could not be reached or returned an error."""


@dataclass(slots=True)
class Station:
    """One groundwater monitoring well."""

    well_id: str
    name: str
    latitude: float
    longitude: float
    distance_km: float
    state_now: int | None
    state_4w: int | None
    state_12w: int | None
    trend_4w: int | None
    quality_code: int | None
    is_reference: bool
    measured_on: date | None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _field(properties: dict, name: str):
    """Read a field by suffix — GRUVO returns fully qualified column names."""
    for key, value in properties.items():
        if key.rsplit(".", 1)[-1] == name:
            return value
    return None


def _to_date(epoch_millis) -> date | None:
    if not epoch_millis:
        return None
    return datetime.fromtimestamp(epoch_millis / 1000, tz=timezone.utc).date()


def _bounding_box(latitude: float, longitude: float, radius_km: float) -> str:
    lat_span = radius_km / 111.0
    # Meridians converge towards the poles, so a degree of longitude is shorter there.
    lon_span = radius_km / (111.0 * max(math.cos(math.radians(latitude)), 0.01))
    return (
        f"{longitude - lon_span:.5f},{latitude - lat_span:.5f},"
        f"{longitude + lon_span:.5f},{latitude + lat_span:.5f}"
    )


async def async_find_nearest(
    session: ClientSession, latitude: float, longitude: float, count: int
) -> list[Station]:
    """The `count` nearest wells that actually carry a classification.

    Wells with no current class (121 of 4 390 at the time of writing) are skipped rather
    than surfaced as an unknown state — a nearby well with no reading is less useful than
    a slightly more distant one with a real one.

    The query is a bounding box, but the *answer* is filtered to the inscribed circle
    before being accepted. That distinction matters: a box of +/- R also catches wells up
    to R*sqrt(2) away in the corners, so simply taking the three nearest hits in the box
    could return a corner well at 26 km while a well 26 km due north — just outside the
    box — was nearer still. Only wells within R of the centre are guaranteed to be the
    complete set at that distance, so unless `count` of them fall inside the circle, the
    search widens.
    """
    candidates: list[Station] = []
    for radius_km in SEARCH_RADII_KM:
        stations = await _async_query_box(session, latitude, longitude, radius_km)
        candidates = usable_sorted(stations)
        confirmed = select_nearest(candidates, count, radius_km)
        if confirmed is not None:
            return confirmed

    # Nothing usable even at the widest radius: for a location abroad this is empty, and
    # the caller drops groundwater entirely.
    return candidates[:count]


def usable_sorted(stations: list[Station]) -> list[Station]:
    """Wells that carry a classification, nearest first."""
    return sorted(
        (station for station in stations if station.state_now is not None),
        key=lambda station: station.distance_km,
    )


def select_nearest(
    candidates: list[Station], count: int, radius_km: float
) -> list[Station] | None:
    """The `count` nearest wells, but only if they are provably the nearest.

    `candidates` came from a bounding box of +/- `radius_km`, which also reaches
    `radius_km * sqrt(2)` into the corners. Only the inscribed circle is complete: every
    well within `radius_km` is certainly in the box, while wells beyond it may or may not
    be, depending on their bearing. So a result is only trustworthy once `count` wells sit
    inside that circle — otherwise a corner hit could be reported as "nearest" while a
    closer well just outside the box went unseen.

    Returns None to mean "not sure yet, widen the search".
    """
    within_circle = [station for station in candidates if station.distance_km <= radius_km]
    if len(within_circle) < count:
        return None
    return within_circle[:count]


async def _async_query_box(
    session: ClientSession, latitude: float, longitude: float, radius_km: float
) -> list[Station]:
    params = {
        "geometry": _bounding_box(latitude, longitude, radius_km),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
    }

    try:
        async with session.get(QUERY_URL, params=params, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise GruvoError(f"GRUVO antwortete mit HTTP {response.status}")
            payload = await response.json(content_type=None)
    except ClientError as err:
        raise GruvoError(f"GRUVO nicht erreichbar: {err}") from err

    if "error" in payload:
        raise GruvoError(str(payload["error"].get("message", "Unbekannter Fehler")))

    stations: list[Station] = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if not coordinates or len(coordinates) < 2:
            continue
        properties = feature.get("properties", {})
        well_id = _field(properties, "well_id")
        if not well_id:
            continue

        lon, lat = float(coordinates[0]), float(coordinates[1])
        stations.append(
            Station(
                well_id=str(well_id),
                name=str(_field(properties, "well_name") or well_id),
                latitude=lat,
                longitude=lon,
                distance_km=haversine_km(latitude, longitude, lat, lon),
                state_now=_field(properties, "state_now_c"),
                state_4w=_field(properties, "state_4w_c"),
                state_12w=_field(properties, "state_12w_c"),
                trend_4w=_field(properties, "change_a_4w_c"),
                quality_code=_field(properties, "state_now_g"),
                is_reference=_field(properties, "rm_cm") == "RM",
                measured_on=_to_date(_field(properties, "step_date")),
            )
        )
    return stations
