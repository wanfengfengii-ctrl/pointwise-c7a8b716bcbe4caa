from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from application.interpolate import interpolate_bias
from application.samples import ValidatedSample
from protocol.limits import ThicknessLimits
from release.curve import NominalCurve


class Disposition(str, Enum):
    PASS = 'pass'
    OUT_OF_LIMITS = 'out_of_limits'
    MISSING = 'missing'
    OUTSIDE_CURVE = 'outside_curve'


@dataclass(frozen=True)
class SampleResult:
    sample_id: str
    disposition: Disposition
    bias: Fraction | None
    corrected_thickness: Fraction | None


def evaluate_sample(sample: ValidatedSample, curve: NominalCurve, limits: ThicknessLimits) -> SampleResult:
    if sample.thickness is None:
        return SampleResult(sample.sample_id, Disposition.MISSING, None, None)
    bias = interpolate_bias(curve, sample.reference)
    if bias is None:
        return SampleResult(sample.sample_id, Disposition.OUTSIDE_CURVE, None, None)
    corrected = sample.thickness - bias
    disposition = Disposition.PASS if limits.contains(corrected) else Disposition.OUT_OF_LIMITS
    return SampleResult(sample.sample_id, disposition, bias, corrected)
