"""Axis-aligned geometry shared by layout, router and lint (drawio units)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def intersects(self, o: "Box", eps: float = 0.0) -> bool:
        """True if the interiors overlap by more than eps on both axes."""
        return self.x < o.right - eps and o.x < self.right - eps and self.y < o.bottom - eps and o.y < self.bottom - eps

    def contains(self, o: "Box", eps: float = 0.0) -> bool:
        return o.x >= self.x - eps and o.y >= self.y - eps and o.right <= self.right + eps and o.bottom <= self.bottom + eps

    def contains_point(self, px: float, py: float, eps: float = 0.0) -> bool:
        """Strict interior test shrunk by eps (boundary points are outside)."""
        return self.x + eps < px < self.right - eps and self.y + eps < py < self.bottom - eps

    def inflate(self, d: float) -> "Box":
        return Box(self.x - d, self.y - d, self.w + 2 * d, self.h + 2 * d)

    def union(self, o: "Box | None") -> "Box":
        if o is None:
            return self
        x, y = min(self.x, o.x), min(self.y, o.y)
        return Box(x, y, max(self.right, o.right) - x, max(self.bottom, o.bottom) - y)

    def translate(self, dx: float, dy: float) -> "Box":
        return Box(self.x + dx, self.y + dy, self.w, self.h)


def segment_hits_box(p: tuple[float, float], q: tuple[float, float], b: Box, eps: float = 0.5) -> bool:
    """Does the axis-parallel segment p-q pass through the interior of b (shrunk by eps)?"""
    (x1, y1), (x2, y2) = p, q
    if abs(y1 - y2) < 1e-9:  # horizontal
        lo, hi = sorted((x1, x2))
        return b.y + eps < y1 < b.bottom - eps and lo < b.right - eps and hi > b.x + eps
    if abs(x1 - x2) < 1e-9:  # vertical
        lo, hi = sorted((y1, y2))
        return b.x + eps < x1 < b.right - eps and lo < b.bottom - eps and hi > b.y + eps
    raise ValueError(f"segment {p}->{q} is not axis-parallel")
