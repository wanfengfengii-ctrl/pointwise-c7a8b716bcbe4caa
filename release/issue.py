import json
from uuid import NAMESPACE_URL, uuid5

from measurement.freezes import get_frozen_calibration, read_frozen_group
from measurement.ledger import CalibrationLedger
from measurement.rows import normalize_trial_batch
from protocol.quantities import CANONICAL_UNIT
from protocol.revisions import ProtocolStore
from release.codec import V1StationPiece, encode_v1
from release.curve import build_nominal_curve
from release.hull import Point, build_hull
from release.v2_codec import EvidenceGroup, V2StationPiece, encode_v2


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


def issue_v2_station_piece(
    ledger: CalibrationLedger, protocols: ProtocolStore, freeze_id: str
) -> bytes:
    """Issue the deterministic V2 piece covering every registered group of a freeze."""
    frozen = get_frozen_calibration(ledger, freeze_id)
    revision = frozen.revision
    if not revision.groups:
        raise ValueError('a V2 station piece needs at least one registered group')
    protocol = protocols.get(revision.protocol_id)
    evidence = []
    for group in revision.groups:
        rows = read_frozen_group(frozen, group.group_id)
        normalized = normalize_trial_batch(rows, protocol.conversion)
        points = tuple(
            Point(row.reference_head - row.gauge, row.thickness_head - row.gauge)
            for row in normalized
        )
        evidence.append(EvidenceGroup(group.group_id, build_hull(points).points))
    identity = json.dumps(
        ['haicen-film-v2', frozen.freeze_id, tuple(group.group_id for group in revision.groups)],
        separators=(',', ':'),
    )
    return encode_v2(V2StationPiece(
        issuance_id=uuid5(NAMESPACE_URL, identity).hex,
        fixture_id=protocol.fixture.fixture_id,
        protocol_id=protocol.protocol_id,
        freeze_id=frozen.freeze_id,
        revision_id=revision.revision_id,
        unit=CANONICAL_UNIT,
        limits=protocol.limits,
        evidence=tuple(evidence),
    ))
