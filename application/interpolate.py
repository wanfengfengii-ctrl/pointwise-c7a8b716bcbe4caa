from bisect import bisect_left
from fractions import Fraction

from protocol.quantities import RationalInput, parse_rational
from release.curve import NominalCurve


def interpolate_bias(curve: NominalCurve, reference: RationalInput) -> Fraction | None:
    reading = parse_rational(reference)
    nodes = curve.nodes
    if reading < nodes[0].reading or reading > nodes[-1].reading:
        return None

    right_index = bisect_left(nodes, reading, key=lambda node: node.reading)
    right = nodes[right_index]
    if reading == right.reading:
        return right.bias
    left = nodes[right_index - 1]
    progress = (reading - left.reading) / (right.reading - left.reading)
    return left.bias + progress * (right.bias - left.bias)
