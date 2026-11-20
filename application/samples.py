from dataclasses import dataclass
from fractions import Fraction

from protocol.fixtures import Fixture, validate_fixture_id, validate_identifier
from protocol.quantities import RationalInput, parse_rational


@dataclass(frozen=True)
class SampleInput:
    sample_id: str
    reference: RationalInput
    thickness: RationalInput | None


@dataclass(frozen=True)
class ValidatedSample:
    sample_id: str
    reference: Fraction
    thickness: Fraction | None


@dataclass(frozen=True)
class ReviewBatch:
    acceptance_id: str
    fixture_id: str
    samples: tuple[SampleInput, ...]


def validate_review_batch(batch: ReviewBatch, piece_fixture_id: str) -> tuple[ValidatedSample, ...]:
    if not isinstance(batch, ReviewBatch):
        raise ValueError('expected a review batch')
    validate_identifier(batch.acceptance_id, 'acceptance id')
    fixture_id = validate_fixture_id(batch.fixture_id)
    if not Fixture(piece_fixture_id).matches(fixture_id):
        raise ValueError('station piece belongs to a different fixture')
    if not isinstance(batch.samples, (tuple, list)) or not batch.samples:
        raise ValueError('review requires a nonempty ordered sample batch')

    accepted = {}
    for sample in batch.samples:
        if not isinstance(sample, SampleInput):
            raise ValueError('expected a sample input')
        sample_id = validate_identifier(sample.sample_id, 'sample id')
        if sample_id in accepted:
            raise ValueError(f'duplicate sample id {sample_id!r}')
        reference = parse_rational(sample.reference)
        thickness = None if sample.thickness is None else parse_rational(sample.thickness)
        accepted[sample_id] = ValidatedSample(sample_id, reference, thickness)
    return tuple(accepted.values())
