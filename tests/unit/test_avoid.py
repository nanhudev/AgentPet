"""Avoidance geometry (§40: never block the user).

Pure functions — no Qt, no Win32 — so the behaviour is verifiable on any box.
"""
from __future__ import annotations

from agentpet.behavior.avoid import (band_for, best_x, conflicts, free_x,
                                     merge_spans, occupied_spans, overlap_ratio)

BOUNDS = (0.0, 0.0, 1920.0, 1040.0)


def test_merge_spans_joins_overlaps():
    assert merge_spans([(100, 200), (150, 300), (400, 500)]) == [(100, 300), (400, 500)]


def test_merge_spans_touching():
    assert merge_spans([(0, 100), (101, 200)]) == [(0, 200)]


def test_band_covers_pet_and_bench():
    top, bottom = band_for(1000.0)
    assert (top, bottom) == (680.0, 1000.0)


def test_occupied_spans_ignores_windows_above_the_band():
    rects = [(100, 50, 800, 400)]          # a window high up on the screen
    assert occupied_spans(rects, 680.0, 1000.0, BOUNDS) == []


def test_occupied_spans_projects_intersecting_windows():
    rects = [(100, 300, 800, 900)]
    spans = occupied_spans(rects, 680.0, 1000.0, BOUNDS)
    assert spans == [(92.0, 808.0)]        # default 8px padding


def test_conflicts_detection():
    spans = [(92.0, 808.0)]
    assert conflicts(600, spans, 480.0)
    assert not conflicts(1500, spans, 480.0)


def test_free_x_steps_aside_to_the_nearest_gap():
    """Idle dodge uses the pet's own width (the bench is folded away)."""
    spans = occupied_spans([(600, 300, 1300, 900)], 680.0, 1000.0, BOUNDS)
    spot = free_x(950.0, spans, BOUNDS, half=60.0)
    assert spot is not None
    assert abs(spot - 950.0) > 40.0                 # it actually moved
    assert not conflicts(spot, spans, 60.0)         # and no longer overlaps


def test_free_x_fits_a_full_bench_on_a_wide_screen():
    wide = (0.0, 0.0, 2560.0, 1400.0)
    spans = occupied_spans([(1200, 300, 1400, 900)], 680.0, 1000.0, wide)
    spot = free_x(1300.0, spans, wide, half=480.0)
    assert spot is not None
    assert not conflicts(spot, spans, 480.0)


def test_free_x_returns_none_when_nothing_fits():
    spans = [(0.0, 1920.0)]
    assert free_x(960.0, spans, BOUNDS, half=480.0) is None


def test_best_x_degrades_to_pet_only_width():
    """A 960px window in the middle: full bench cannot fit, the pet can."""
    spans = occupied_spans([(400, 200, 1360, 950)], 680.0, 1000.0, BOUNDS)
    spot = best_x(880.0, spans, BOUNDS, deployed=True)
    assert spot is not None
    assert not conflicts(spot, spans, 60.0)


def test_best_x_prefers_a_free_spot_over_staying():
    spans = occupied_spans([(0, 200, 700, 1000)], 680.0, 1000.0, BOUNDS)
    spot = best_x(300.0, spans, BOUNDS, deployed=False)
    assert spot is not None
    assert not conflicts(spot, spans, 60.0)


def test_overlap_ratio():
    assert overlap_ratio((0, 0, 100, 100), (50, 50, 150, 150)) == 0.25
    assert overlap_ratio((0, 0, 100, 100), (0, 0, 100, 100)) == 1.0
    assert overlap_ratio((0, 0, 100, 100), (200, 200, 300, 300)) == 0.0
