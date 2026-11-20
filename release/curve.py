from collections.abc import Iterable
from dataclasses import dataclass

from measurement.rows import NormalizedTrialRow
from protocol.quantities import RationalInput, parse_rational


@dataclass(frozen=True)
class CurveNode:
    reading: RationalInput
    bias: RationalInput

    def __post_init__(self) -> None:
        object.__setattr__(self, 'reading', parse_rational(self.reading))
        object.__setattr__(self, 'bias', parse_rational(self.bias))


@dataclass(frozen=True)
class NominalCurve:
    nodes: tuple[CurveNode, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.nodes, (tuple, list)) or not self.nodes:
            raise ValueError('a nominal curve needs at least one node')
        nodes = tuple(self.nodes)
        if any(not isinstance(node, CurveNode) for node in nodes):
            raise ValueError('invalid nominal curve node')
        if any(left.reading >= right.reading for left, right in zip(nodes, nodes[1:])):
            raise ValueError('curve readings must be strictly increasing')
        object.__setattr__(self, 'nodes', nodes)


def build_nominal_curve(rows: Iterable[NormalizedTrialRow]) -> NominalCurve:
    by_reading = {}
    for row in rows:
        reading = row.reference_head - row.gauge
        bias = row.thickness_head - row.gauge
        if reading in by_reading and by_reading[reading] != bias:
            raise ValueError(f'multiple thickness biases at reference reading {reading}')
        by_reading[reading] = bias
    return NominalCurve(tuple(CurveNode(reading, by_reading[reading]) for reading in sorted(by_reading)))
