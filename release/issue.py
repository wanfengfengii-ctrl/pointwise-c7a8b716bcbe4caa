import json
from uuid import NAMESPACE_URL, uuid5

from measurement.freezes import get_frozen_calibration, read_frozen_group
from measurement.ledger import CalibrationLedger
from measurement.rows import normalize_trial_batch
from protocol.quantities import CANONICAL_UNIT
from protocol.revisions import ProtocolStore
from release.codec import V1StationPiece, encode_v1
from release.curve import build_nominal_curve


def issue_v1_station_piece(
    ledger: CalibrationLedger, protocols: ProtocolStore, freeze_id: str, group_id: str
) -> bytes:
    frozen = get_frozen_calibration(ledger, freeze_id)
    rows = read_frozen_group(frozen, group_id)
    protocol = protocols.get(frozen.revision.protocol_id)
    curve = build_nominal_curve(normalize_trial_batch(rows, protocol.conversion))
    identity = json.dumps(['haicen-film-v1', frozen.freeze_id, group_id], separators=(',', ':'))
    return encode_v1(V1StationPiece(
        issuance_id=uuid5(NAMESPACE_URL, identity).hex,
        fixture_id=protocol.fixture.fixture_id,
        protocol_id=protocol.protocol_id,
        freeze_id=frozen.freeze_id,
        revision_id=frozen.revision.revision_id,
        group_id=group_id,
        unit=CANONICAL_UNIT,
        limits=protocol.limits,
        curve=curve,
    ))
