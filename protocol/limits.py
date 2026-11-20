from dataclasses import dataclass

from protocol.quantities import RationalInput, parse_rational


@dataclass(frozen=True)
class ThicknessLimits:
    lower: RationalInput
    upper: RationalInput

    def __post_init__(self) -> None:
        lower = parse_rational(self.lower)
        upper = parse_rational(self.upper)
        if lower > upper:
            raise ValueError('thickness limits must be ordered')
        object.__setattr__(self, 'lower', lower)
        object.__setattr__(self, 'upper', upper)

    def contains(self, value: RationalInput) -> bool:
        return self.lower <= parse_rational(value) <= self.upper
