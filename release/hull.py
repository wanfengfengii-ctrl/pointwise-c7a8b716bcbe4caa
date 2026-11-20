"""Closed convex hulls of normalized (reference reading, thickness bias) pairs.

A V2 group keeps the joint relation of every pair in its closed convex hull:
the hull contains its vertices, the line segments between them and the
vertical sections at either reading extreme.  Each envelope is stored as a
piecewise-linear chain whose readings are strictly increasing, so evaluating
the supporting bias interval at any reading only needs rational arithmetic.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from protocol.quantities import parse_rational


@dataclass(frozen=True)
class Point:
    x: Fraction
    y: Fraction

    def __post_init__(self) -> None:
        object.__setattr__(self, 'x', parse_rational(self.x))
        object.__setattr__(self, 'y', parse_rational(self.y))


def _cross(origin: Point, left: Point, right: Point) -> Fraction:
    return ((left.x - origin.x) * (right.y - origin.y)
            - (left.y - origin.y) * (right.x - origin.x))


def _lower_envelope(points: tuple[Point, ...]) -> tuple[Point, ...]:
    chain: list[Point] = []
    for point in points:
        if chain and chain[-1].x == point.x:
            if len(chain) == 1:
                # A vertical section: both extremes belong to the closed hull.
                chain.append(point)
            continue
        while len(chain) >= 2 and _cross(chain[-2], chain[-1], point) < 0:
            chain.pop()
        chain.append(point)
    return tuple(chain)


def _upper_envelope(points: tuple[Point, ...]) -> tuple[Point, ...]:
    # Build the lower envelope of the mirrored points and mirror it back.
    mirrored = tuple(sorted((Point(point.x, -point.y) for point in points),
                            key=lambda point: (point.x, point.y)))
    chain: list[Point] = []
    for point in mirrored:
        if chain and chain[-1].x == point.x:
            if len(chain) == 1:
                chain.append(point)
            continue
        while len(chain) >= 2 and _cross(chain[-2], chain[-1], point) < 0:
            chain.pop()
        chain.append(point)
    return tuple(Point(point.x, -point.y) for point in chain)


@dataclass(frozen=True)
class ConvexHull:
    lower: tuple[Point, ...]
    upper: tuple[Point, ...]

    @property
    def x_min(self) -> Fraction:
        return self.lower[0].x

    @property
    def x_max(self) -> Fraction:
        return self.lower[-1].x

    @property
    def points(self) -> tuple[Point, ...]:
        """All hull vertices, lexicographically sorted and deduplicated."""
        return tuple(sorted({*self.lower, *self.upper}, key=lambda point: (point.x, point.y)))

    def supports(self, reading: Fraction) -> bool:
        return self.x_min <= reading <= self.x_max

    def evaluate(self, chain: tuple[Point, ...], reading: Fraction) -> Fraction:
        if len(chain) == 1:
            if reading != chain[0].x:
                raise ValueError('reading is outside the hull domain')
            return chain[0].y
        for index in range(len(chain) - 1):
            left, right = chain[index], chain[index + 1]
            if left.x <= reading <= right.x:
                if right.x == left.x:
                    return left.y
                progress = (reading - left.x) / (right.x - left.x)
                return left.y + progress * (right.y - left.y)
        raise ValueError('reading is outside the hull domain')

    def edge_lines_over(
        self, chain: tuple[Point, ...], left: Fraction, right: Fraction,
    ) -> tuple[tuple[Fraction, Fraction], ...]:
        """Edge lines whose non-vertical domain meets the open interval (left, right)."""
        if len(chain) == 1:
            if left < chain[0].x < right:
                return (Fraction(0), chain[0].y),
            return ()
        lines = []
        for edge_left, edge_right in zip(chain, chain[1:]):
            if edge_right.x == edge_left.x:
                continue
            if edge_left.x < right and edge_right.x > left:
                slope = (edge_right.y - edge_left.y) / (edge_right.x - edge_left.x)
                lines.append((slope, edge_left.y - slope * edge_left.x))
        return tuple(lines)

    def bias_interval(self, reading: Fraction) -> tuple[Fraction, Fraction]:
        if not self.supports(reading):
            raise ValueError('reading is outside the hull domain')
        if reading == self.x_min:
            low = min(point.y for point in self.lower if point.x == reading)
            high = max(point.y for point in self.upper if point.x == reading)
            return low, high
        if reading == self.x_max:
            low = min(point.y for point in self.lower if point.x == reading)
            high = max(point.y for point in self.upper if point.x == reading)
            return low, high
        return self.evaluate(self.lower, reading), self.evaluate(self.upper, reading)


def build_hull(points: Iterable[Point]) -> ConvexHull:
    unique = tuple(sorted(set(points), key=lambda point: (point.x, point.y)))
    if not unique:
        raise ValueError('a convex hull needs at least one point')
    return ConvexHull(_lower_envelope(unique), _upper_envelope(unique))
