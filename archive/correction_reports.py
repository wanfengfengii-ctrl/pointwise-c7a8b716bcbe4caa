import json
from uuid import uuid4

from archive.receipts import SignatureReceipt, write_correction_receipt
from archive.storage import ArchiveStorage
from protocol.fixtures import validate_identifier
from release.codec import decode_station_piece
from release.inventory import AcceptedPiece
from release.v2_codec import V2StationPiece


def capture_correction_provenance(accepted: AcceptedPiece) -> dict:
    piece = accepted.piece
    if not isinstance(piece, V2StationPiece):
        raise ValueError('correction tables require a V2 station piece')
    return {
        'acceptance_id': accepted.acceptance_id,
        'issuance_id': piece.issuance_id,
        'fixture_id': piece.fixture_id,
        'protocol_id': piece.protocol_id,
        'freeze_id': piece.freeze_id,
        'revision_id': piece.revision_id,
    }


def validate_correction_provenance(provenance: dict, original_bytes: bytes) -> None:
    expected_fields = frozenset((
        'acceptance_id', 'issuance_id', 'fixture_id', 'protocol_id', 'freeze_id', 'revision_id',
    ))
    if not isinstance(provenance, dict) or frozenset(provenance) != expected_fields:
        raise ValueError('correction provenance does not match its station piece')
    for field in expected_fields:
        validate_identifier(provenance[field], field)
    piece = decode_station_piece(original_bytes)
    if not isinstance(piece, V2StationPiece):
        raise ValueError('correction provenance does not match its station piece')
    expected = {
        'acceptance_id': provenance['acceptance_id'],
        'issuance_id': piece.issuance_id,
        'fixture_id': piece.fixture_id,
        'protocol_id': piece.protocol_id,
        'freeze_id': piece.freeze_id,
        'revision_id': piece.revision_id,
    }
    if expected != provenance:
        raise ValueError('correction provenance does not match its station piece')

def publish_correction_report(
    storage: ArchiveStorage, body: dict, provenance: dict, original_bytes: bytes
) -> tuple[dict, SignatureReceipt]:
    validate_correction_provenance(provenance, original_bytes)
    report_id = uuid4().hex
    body = {**body, 'report_id': report_id, 'provenance': provenance}
    encoded = json.dumps(body, sort_keys=True, separators=(',', ':'))
    with storage.transaction() as connection:
        connection.execute(
            'INSERT INTO correction_reports VALUES (?, ?, ?)',
            (report_id, encoded, original_bytes),
        )
        receipt = write_correction_receipt(connection, report_id)
    return body, receipt


def read_correction_report(storage: ArchiveStorage, report_id: str) -> tuple[dict, bytes]:
    validate_identifier(report_id, 'report id')
    row = storage.connection.execute(
        'SELECT body, piece_bytes FROM correction_reports WHERE report_id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise KeyError(report_id)
    payload, original_bytes = row
    return json.loads(payload), original_bytes
