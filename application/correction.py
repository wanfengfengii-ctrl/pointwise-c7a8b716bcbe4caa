"""Partition a closed reading window into correction states.

For every reading the union of the group hulls supplies a closed interval of
compatible thickness biases.  A correction is feasible exactly when the closed
correction-limit interval and every bias residual interval share a point.  The
window is cut at hull breakpoints and at envelope-line crossings so that each
emitted segment keeps fixed open/closed endpoints and one affine instruction.
"""
from fractions import Fraction

from protocol.quantities import parse_rational
from release.hull import ConvexHull


NO_EVIDENCE = 'no_evidence'
UNCORRECTABLE = 'uncorrectable'
CORRECTABLE = 'correctable'


def _ordered_pair(value: object, label: str) -> tuple[Fraction, Fraction]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f'{label} must be a pair of rational values')
    left, right = parse_rational(value[0]), parse_rational(value[1])
    if left > right:
        raise ValueError(f'{label} endpoints must be ordered')
    return left, right


def parse_request(window: object, limits: object, tolerance: object) -> tuple[
    tuple[Fraction, Fraction], tuple[Fraction, Fraction], Fraction
]:
    reading_window = _ordered_pair(window, 'reading window')
    correction_limits = _ordered_pair(limits, 'correction limits')
    bound = parse_rational(tolerance)
    if bound < 0:
        raise ValueError('tolerance must be non-negative')
    return reading_window, correction_limits, bound


def _feasible_interval(
    hulls: tuple[ConvexHull, ...], reading: Fraction,
    limits: tuple[Fraction, Fraction], tolerance: Fraction,
) -> tuple[Fraction, Fraction] | None:
    # For a compatible bias interval [bL, bH], one correction c covers every
    # bias exactly when bH - tol <= c <= bL + tol (closed, equality accepted).
    lower, upper = limits
    for hull in hulls:
        if hull.supports(reading):
            bias_low, bias_high = hull.bias_interval(reading)
            lower = max(lower, bias_high - tolerance)
            upper = min(upper, bias_low + tolerance)
    if lower > upper:
        return None
    return lower, upper


def _crossing(
    first: tuple[Fraction, Fraction], second: tuple[Fraction, Fraction],
    left: Fraction, right: Fraction,
) -> Fraction | None:
    first_slope, first_intercept = first
    second_slope, second_intercept = second
    if first_slope == second_slope:
        return None
    crossing = (second_intercept - first_intercept) / (first_slope - second_slope)
    if left < crossing < right:
        return crossing
    return None


def _point_segment(
    reading: Fraction, hulls: tuple[ConvexHull, ...],
    limits: tuple[Fraction, Fraction], tolerance: Fraction,
) -> list:
    if not any(hull.supports(reading) for hull in hulls):
        return [reading, reading, True, True, NO_EVIDENCE, None]
    feasible = _feasible_interval(hulls, reading, limits, tolerance)
    if feasible is None:
        return [reading, reading, True, True, UNCORRECTABLE, None]
    correction = feasible[0]
    return [reading, reading, True, True, CORRECTABLE, [Fraction(0), correction]]


def _open_cell(
    left: Fraction, right: Fraction, hulls: tuple[ConvexHull, ...],
    limits: tuple[Fraction, Fraction], tolerance: Fraction,
) -> list:
    # A hull meeting the open cell at all is active throughout its interior.
    supporting = tuple(
        hull for hull in hulls if hull.x_min < right and hull.x_max > left
    )
    if not supporting:
        return [[left, right, False, False, NO_EVIDENCE, None]], ()

    # Collect the envelope edges that actually meet this open cell.  Taking the
    # pointwise max/min over exactly those lines reproduces the true corridor.
    low_chain_lines: list[tuple[Fraction, Fraction]] = []
    high_chain_lines: list[tuple[Fraction, Fraction]] = []
    for hull in supporting:
        low_chain_lines.extend(hull.edge_lines_over(hull.lower, left, right))
        high_chain_lines.extend(hull.edge_lines_over(hull.upper, left, right))
    # The shared-correction corridor is [max(bH - tol, limit_low),
    # min(bL + tol, limit_high)] over every interior-active hull.
    lower_lines = [
        (slope, intercept - tolerance) for slope, intercept in high_chain_lines
    ]
    upper_lines = [
        (slope, intercept + tolerance) for slope, intercept in low_chain_lines
    ]
    lower_lines.append((Fraction(0), limits[0]))
    upper_lines.append((Fraction(0), limits[1]))

    cuts = {left, right}
    all_lines = lower_lines + upper_lines
    for index, line in enumerate(all_lines):
        for other in all_lines[index + 1:]:
            crossing = _crossing(line, other, left, right)
            if crossing is not None:
                cuts.add(crossing)

    boundaries = sorted(cuts)
    interior_cuts = tuple(value for value in boundaries if left < value < right)
    segments = []
    for cell_left, cell_right in zip(boundaries, boundaries[1:]):
        cell_mid = (cell_left + cell_right) / 2
        active_lower = max(lower_lines, key=lambda line: line[0] * cell_mid + line[1])
        active_upper = min(upper_lines, key=lambda line: line[0] * cell_mid + line[1])
        # With fixed active lines the corridor width is affine over the cell,
        # so feasibility holds throughout exactly when both ends are feasible.
        lower_left = active_lower[0] * cell_left + active_lower[1]
        upper_left = active_upper[0] * cell_left + active_upper[1]
        lower_right = active_lower[0] * cell_right + active_lower[1]
        upper_right = active_upper[0] * cell_right + active_upper[1]
        if lower_left > upper_left or lower_right > upper_right:
            segments.append([cell_left, cell_right, False, False, UNCORRECTABLE, None])
        else:
            segments.append([cell_left, cell_right, False, False, CORRECTABLE, list(active_lower)])
    return segments, interior_cuts


def _segment_order(record: list) -> tuple:
    left, right, left_closed, right_closed, state, instruction = record
    # The closed singleton at a boundary comes first, then the open segment
    # starting there; open segments otherwise stay ordered by their readings.
    if left == right:
        return left, 0, right
    return left, 1, right


def build_segments(
    hulls: tuple[ConvexHull, ...],
    window: tuple[Fraction, Fraction],
    limits: tuple[Fraction, Fraction],
    tolerance: Fraction,
) -> list:
    (window_left, window_right), _, _ = parse_request(window, limits, tolerance)
    if window_left == window_right:
        return [_point_segment(window_left, hulls, limits, tolerance)]

    cuts = {window_left, window_right}
    for hull in hulls:
        # Hull domain boundaries and every envelope breakpoint, so inside each
        # open cell every active hull is represented by a single affine edge.
        for point in hull.points:
            if window_left < point.x < window_right:
                cuts.add(point.x)
    boundaries = sorted(cuts)

    records = [_point_segment(window_left, hulls, limits, tolerance)]
    point_readings = {window_left}
    for left, right in zip(boundaries, boundaries[1:]):
        open_segments, interior_cuts = _open_cell(left, right, hulls, limits, tolerance)
        records.extend(open_segments)
        for cut in (*interior_cuts, right):
            if cut not in point_readings:
                point_readings.add(cut)
                records.append(_point_segment(cut, hulls, limits, tolerance))
    return sorted(records, key=_segment_order)
