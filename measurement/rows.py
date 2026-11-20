from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from protocol.fixtures import validate_identifier
from protocol.quantities import RationalInput, UnitConversion, parse_rational


@dataclass(frozen=True)
class TrialRow:
    row_id: str
    unit: str
    reference_head: RationalInput
    gauge: RationalInput
    thickness_head: RationalInput

    def __post_init__(self) -> None:
        validate_identifier(self.row_id, 'trial id')
        validate_identifier(self.unit, 'trial unit')
        for field in ('reference_head', 'gauge', 'thickness_head'):
            object.__setattr__(self, field, parse_rational(getattr(self, field)))


@dataclass(frozen=True)
class NormalizedTrialRow:
    row_id: str
    reference_head: Fraction
    gauge: Fraction
    thickness_head: Fraction


def normalize_trial_row(row: TrialRow, conversion: UnitConversion) -> NormalizedTrialRow:
    if not isinstance(row, TrialRow):
        raise ValueError('expected a trial row')
    return NormalizedTrialRow(
        row.row_id,
        conversion.normalize(row.reference_head, row.unit),
        conversion.normalize(row.gauge, row.unit),
        conversion.normalize(row.thickness_head, row.unit),
    )


def normalize_trial_batch(
    rows: Iterable[TrialRow], conversion: UnitConversion
) -> tuple[NormalizedTrialRow, ...]:
    normalized = []
    seen = set()
    for row in rows:
        result = normalize_trial_row(row, conversion)
        if result.row_id in seen:
            raise ValueError(f'duplicate trial id {result.row_id!r}')
        seen.add(result.row_id)
        normalized.append(result)
    return tuple(normalized)
