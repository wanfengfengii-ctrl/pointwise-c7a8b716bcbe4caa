from dataclasses import dataclass
from fractions import Fraction
import re

CANONICAL_UNIT = 'μm'
RationalInput = Fraction | int | str
_RATIONAL_TEXT = re.compile(r'[+-]?[0-9]+(?:/[0-9]+|\.[0-9]+)?')


def parse_rational(value: object) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str) and _RATIONAL_TEXT.fullmatch(value):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError(f'invalid rational value {value!r}') from error
    raise ValueError(f'invalid rational value {value!r}')


def format_rational(value: RationalInput) -> str:
    return str(parse_rational(value))


@dataclass(frozen=True)
class UnitConversion:
    unit: str
    multiplier: RationalInput

    def __post_init__(self) -> None:
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError('a source unit is required')
        multiplier = parse_rational(self.multiplier)
        if multiplier <= 0 or (self.unit == CANONICAL_UNIT and multiplier != 1):
            raise ValueError('invalid unit multiplier')
        object.__setattr__(self, 'multiplier', multiplier)

    def normalize(self, value: RationalInput, unit: str) -> Fraction:
        if unit != self.unit:
            raise ValueError(f'expected source unit {self.unit!r}, received {unit!r}')
        return parse_rational(value) * self.multiplier
