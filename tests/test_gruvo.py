"""Tests for the groundwater well selection."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.klima_at_home.api.gruvo import (  # noqa: E402
    Station,
    haversine_km,
    select_nearest,
    usable_sorted,
)
from custom_components.klima_at_home.const import GW_STATE_CLASSES  # noqa: E402


def _station(name: str, distance_km: float, state_now: int | None = 3) -> Station:
    return Station(
        well_id=name,
        name=name,
        latitude=51.0,
        longitude=9.0,
        distance_km=distance_km,
        state_now=state_now,
        state_4w=3,
        state_12w=3,
        trend_4w=3,
        quality_code=2,
        is_reference=False,
        measured_on=date(2026, 7, 1),
    )


def test_haversine_against_a_known_distance():
    # Kassel -> Berlin, great-circle, is ~300 km. (Not the ~360 km you would drive — the
    # wells are found by straight-line distance, so that is what is checked.)
    distance = haversine_km(51.3127, 9.4797, 52.5200, 13.4050)
    assert 295.0 < distance < 306.0, distance

    assert haversine_km(51.0, 9.0, 51.0, 9.0) == 0.0


def test_wells_without_a_classification_are_dropped():
    stations = [
        _station("kein_wert", 1.0, state_now=None),
        _station("nah", 5.0),
        _station("fern", 9.0),
    ]
    usable = usable_sorted(stations)
    assert [s.well_id for s in usable] == ["nah", "fern"]


def test_selection_returns_the_nearest_inside_the_circle():
    candidates = usable_sorted([_station("a", 3.0), _station("b", 7.0), _station("c", 9.0)])
    assert [s.well_id for s in select_nearest(candidates, 2, radius_km=25.0)] == ["a", "b"]


def test_selection_refuses_to_answer_from_the_box_corners_alone():
    # This is the bug the circle check exists for. All three hits came out of a +/- 25 km
    # bounding box, but they sit in its corners, beyond 25 km. A well 26 km due north
    # would be nearer than the 26.1 km one here — and would NOT have been in the box. So
    # answering now could name the wrong "nearest" well.
    corners = usable_sorted([_station("a", 25.0), _station("b", 25.6), _station("c", 26.1)])

    assert select_nearest(corners, 3, radius_km=25.0) is None, (
        "must widen the search rather than trust wells beyond the inscribed circle"
    )

    # Widened to 50 km, the same three are now provably complete.
    chosen = select_nearest(corners, 3, radius_km=50.0)
    assert [s.well_id for s in chosen] == ["a", "b", "c"]


def test_selection_needs_enough_wells_inside_the_circle():
    candidates = usable_sorted([_station("a", 10.0), _station("b", 30.0)])
    assert select_nearest(candidates, 3, radius_km=25.0) is None
    assert select_nearest(candidates, 1, radius_km=25.0)[0].well_id == "a"


def test_every_bgr_class_maps_to_a_name_and_nothing_else_does():
    assert GW_STATE_CLASSES[1] == "sehr_niedrig"
    assert GW_STATE_CLASSES[3] == "normal"
    assert GW_STATE_CLASSES[5] == "sehr_hoch"
    assert len(GW_STATE_CLASSES) == 5
    # An unknown code must not fall back to a class — 121 of GRUVO's wells carry none,
    # and quietly calling those "normal" would be a lie on the dashboard.
    assert GW_STATE_CLASSES.get(None) is None
    assert GW_STATE_CLASSES.get(0) is None
    assert GW_STATE_CLASSES.get(6) is None
