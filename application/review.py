from application.correction import (
    CORRECTABLE, NO_EVIDENCE, UNCORRECTABLE, build_segments, parse_request,
)
from application.disposition import evaluate_sample
from application.samples import ReviewBatch, validate_review_batch
from archive.correction_reports import (
    capture_correction_provenance, publish_correction_report,
)
from archive.provenance import capture_provenance
from archive.receipts import SignatureReceipt
from archive.reports import ReviewReport, publish_report
from archive.storage import ArchiveStorage
from fractions import Fraction
from protocol.quantities import format_rational, parse_rational
from release.admission import get_accepted_piece
from release.codec import V1StationPiece
from release.hull import build_hull
from release.inventory import AdmissionInventory
from release.v2_codec import V2StationPiece


def sign_review(
    inventory: AdmissionInventory, storage: ArchiveStorage, batch: ReviewBatch
) -> tuple[ReviewReport, SignatureReceipt]:
    if not isinstance(batch, ReviewBatch):
        raise ValueError('expected a review batch')
    accepted = get_accepted_piece(inventory, batch.acceptance_id)
    piece = accepted.piece
    if not isinstance(piece, V1StationPiece):
        raise ValueError('V1 sample reviews require a V1 station piece')
    samples = validate_review_batch(batch, piece.fixture_id)
    results = tuple(evaluate_sample(sample, piece.curve, piece.limits) for sample in samples)
    return publish_report(storage, samples, results, capture_provenance(accepted))


def _encode_segments(segments: list) -> list:
    encoded = []
    for left, right, left_closed, right_closed, state, instruction in segments:
        encoded.append([
            format_rational(left), format_rational(right),
            bool(left_closed), bool(right_closed), state,
            None if instruction is None else [
                format_rational(instruction[0]), format_rational(instruction[1]),
            ],
        ])
    return encoded


def sign_correction(
    inventory: AdmissionInventory,
    storage: ArchiveStorage,
    acceptance_id: object,
    window: object,
    limits: object,
    tolerance: object,
) -> tuple[dict, SignatureReceipt]:
    if not isinstance(acceptance_id, str) or not acceptance_id.strip():
        raise ValueError('acceptance id must be a nonempty string')
    reading_window, correction_limits, bound = parse_request(window, limits, tolerance)
    accepted = get_accepted_piece(inventory, acceptance_id)
    piece = accepted.piece
    if not isinstance(piece, V2StationPiece):
        raise ValueError('correction tables require a V2 station piece')

    hulls = tuple(build_hull(group.vertices) for group in piece.evidence)
    segments = build_segments(hulls, reading_window, correction_limits, bound)
    body = {
        'window': [format_rational(reading_window[0]), format_rational(reading_window[1])],
        'limits': [format_rational(correction_limits[0]), format_rational(correction_limits[1])],
        'tolerance': format_rational(bound),
        'segments': _encode_segments(segments),
    }
    provenance = capture_correction_provenance(accepted)
    return publish_correction_report(storage, body, provenance, accepted.original_bytes)


def _decode_segments(body: dict) -> list:
    segments = []
    for record in body['segments']:
        if not isinstance(record, list) or len(record) != 6:
            raise ValueError('invalid correction segment record')
        left, right, left_closed, right_closed, state, instruction = record
        if type(left_closed) is not bool or type(right_closed) is not bool or state not in (
            CORRECTABLE, UNCORRECTABLE, NO_EVIDENCE,
        ):
            raise ValueError('invalid correction segment record')
        decoded_instruction = None
        if state == CORRECTABLE:
            if instruction is None or not isinstance(instruction, list) or len(instruction) != 2:
                raise ValueError('a correctable segment must carry an instruction')
            decoded_instruction = [parse_rational(instruction[0]), parse_rational(instruction[1])]
        elif instruction is not None:
            raise ValueError('only correctable segments carry instructions')
        segments.append([
            parse_rational(left), parse_rational(right),
            left_closed, right_closed, state, decoded_instruction,
        ])
    return segments


def lookup_correction(body: dict, reading: object) -> tuple[str, Fraction | None]:
    if not isinstance(body, dict):
        raise ValueError('a correction table body is required')
    try:
        window_left, window_right = (parse_rational(value) for value in body['window'])
        segments = _decode_segments(body)
    except (KeyError, TypeError) as error:
        raise ValueError('invalid correction table body') from error
    value = parse_rational(reading)
    if value < window_left or value > window_right:
        raise ValueError('reading is outside the signed reading window')

    for left, right, left_closed, right_closed, state, instruction in segments:
        inside_left = (value >= left) if left_closed else (value > left)
        inside_right = (value <= right) if right_closed else (value < right)
        if inside_left and inside_right:
            if state != CORRECTABLE:
                return state, None
            slope, intercept = instruction
            return CORRECTABLE, slope * value + intercept
    raise ValueError('the correction table does not cover the reading')
