from dataclasses import dataclass

from protocol.fixtures import validate_identifier
from release.codec import decode_v1
from release.inventory import AcceptedPiece


@dataclass(frozen=True)
class ReviewProvenance:
    acceptance_id: str
    issuance_id: str
    fixture_id: str
    protocol_id: str
    freeze_id: str
    revision_id: str
    group_id: str
    original_bytes: bytes


def capture_provenance(accepted: AcceptedPiece) -> ReviewProvenance:
    piece = accepted.piece
    return ReviewProvenance(
        acceptance_id=accepted.acceptance_id,
        issuance_id=piece.issuance_id,
        fixture_id=piece.fixture_id,
        protocol_id=piece.protocol_id,
        freeze_id=piece.freeze_id,
        revision_id=piece.revision_id,
        group_id=piece.group_id,
        original_bytes=accepted.original_bytes,
    )


def validate_provenance(provenance: ReviewProvenance) -> None:
    validate_identifier(provenance.acceptance_id, 'acceptance id')
    piece = decode_v1(provenance.original_bytes)
    expected = capture_provenance(AcceptedPiece(provenance.acceptance_id, provenance.original_bytes, piece))
    if expected != provenance:
        raise ValueError('report provenance does not match its station piece')
