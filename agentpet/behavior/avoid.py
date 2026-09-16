"""Pure geometry for "get out of the user's way" (no Qt, no Win32 — testable).

The pet lives on a 1-D ground line, so avoidance reduces to: given the
horizontal spans that application windows occupy along the pet's band, find
the nearest x where the pet (plus its docked workbench) fits without covering
any of them.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

ShellRect = Tuple[float, float, float, float]   # left, top, right, bottom
Span = Tuple[float, float]

# The workbench extends ~470px left and ~450px right of the pet when deployed.
WORKBENCH_HALF_WIDTH = 480.0
_PET_ONLY_HALF = 60.0
_FALLBACK_STEPS = (480.0, 360.0, 240.0, 140.0, 60.0)


def overlap_area(a: ShellRect, b: ShellRect) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if (w > 0 and h > 0) else 0.0


def overlap_ratio(a: ShellRect, b: ShellRect) -> float:
    """Fraction of ``a`` that is covered by ``b`` (0..1)."""
    area = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
    return min(1.0, overlap_area(a, b) / area)


def merge_spans(spans: Iterable[Span]) -> List[Span]:
    out: List[Span] = []
    for s, e in sorted(spans):
        if e <= s:
            continue
        if out and s <= out[-1][1] + 1.0:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def occupied_spans(rects: Sequence[ShellRect], band_top: float,
                   band_bottom: float, bounds: Optional[ShellRect] = None,
                   pad: float = 8.0) -> List[Span]:
    """Project the window rectangles that intersect the pet's band onto x."""
    spans: List[Span] = []
    for l, t, r, b in rects:
        if b <= band_top or t >= band_bottom:
            continue                        # does not reach the pet's band
        spans.append((l - pad, r + pad))
    if bounds is not None:
        spans = [(max(bounds[0], s), min(bounds[2], e)) for s, e in spans]
    return merge_spans(spans)


def conflicts(x: float, spans: Sequence[Span], half: float) -> bool:
    l, r = x - half, x + half
    for s, e in spans:
        if l < e and r > s:
            return True
    return False


def free_x(desired: float, spans: Sequence[Span], bounds: ShellRect,
           half: float = WORKBENCH_HALF_WIDTH,
           step: float = 24.0) -> Optional[float]:
    """Nearest x to ``desired`` where a width of ``2*half`` fits between spans.

    Returns ``None`` when nothing fits — the caller then retries with a
    narrower half-width (pet only) instead of giving up.
    """
    left, right = bounds[0], bounds[2]
    if right - left < 2 * half:
        return None
    lo, hi = left + half, right - half
    if lo > hi:
        return None
    target = min(max(desired, lo), hi)
    if not conflicts(target, spans, half):
        return target
    # walk outwards from the desired position, then fall back to any slot
    d = step
    limit = (hi - lo) / step + 2
    i = 0
    while i < limit and d <= (hi - lo) + step:
        for cand in (target - d, target + d):
            if lo <= cand <= hi and not conflicts(cand, spans, half):
                return cand
        d += step
        i += 1
    for cand in [c * step + lo for c in range(int((hi - lo) / step) + 1)]:
        if not conflicts(min(cand, hi), spans, half):
            return min(cand, hi)
    return None


def best_x(desired: float, spans: Sequence[Span], bounds: ShellRect,
           deployed: bool) -> Optional[float]:
    """Pick a spot, degrading gracefully: full bench -> narrower -> pet only.

    When idle the pet itself only needs ~80px (two pets can share the gap
    between an open bench and the screen edge)."""
    halves = _FALLBACK_STEPS if deployed else (60.0, 40.0)
    for half in halves:
        spot = free_x(desired, spans, bounds, half)
        if spot is not None:
            return spot
    return None


def band_for(ground_y: float, height: float = 320.0) -> Tuple[float, float]:
    """Vertical band the pet + its workbench can occupy above the ground."""
    return (ground_y - height, ground_y)
