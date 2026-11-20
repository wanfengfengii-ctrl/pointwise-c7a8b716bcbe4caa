from dataclasses import dataclass
import json

from protocol.fixtures import validate_fixture_id, validate_identifier
from protocol.limits import ThicknessLimits
from protocol.quantities import CANONICAL_UNIT, format_rational, parse_rational
from release.curve import CurveNode, NominalCurve
from release.v2_codec import V2StationPiece, decode_v2


_ID_FIELDS = ('issuance_id', 'fixture_id', 'protocol_id', 'freeze_id', 'revision_id', 'group_id')
_FIELDS = {*_ID_FIELDS, 'version', 'unit', 'limits', 'nodes'}


@dataclass(frozen=True)
class V1StationPiece:
    issuance_id: str
    fixture_id: str
    protocol_id: str
    freeze_id: str
    revision_id: str
    group_id: str
    unit: str
    limits: ThicknessLimits
    curve: NominalCurve

    def __post_init__(self) -> None:
        validate_fixture_id(self.fixture_id)
        for field in _ID_FIELDS:
            validate_identifier(getattr(self, field), field)
        if self.unit != CANONICAL_UNIT:
            raise ValueError('unexpected station piece unit')
        if not isinstance(self.limits, ThicknessLimits) or not isinstance(self.curve, NominalCurve):
            raise ValueError('station piece requires thickness limits and a nominal curve')


def encode_v1(piece: V1StationPiece) -> bytes:
    if not isinstance(piece, V1StationPiece):
        raise ValueError('expected a V1 station piece')
    body = {field: getattr(piece, field) for field in _ID_FIELDS}
    body.update(
        version=1,
        unit=piece.unit,
        limits=[format_rational(piece.limits.lower), format_rational(piece.limits.upper)],
        nodes=[[format_rational(node.reading), format_rational(node.bias)] for node in piece.curve.nodes],
    )
    return json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate station piece field {key!r}')
        result[key] = value
    return result


def _rational_pair(value: object) -> tuple:
    if not isinstance(value, list) or len(value) != 2 or any(type(item) is not str for item in value):
        raise ValueError('expected a pair of rational strings')
    return parse_rational(value[0]), parse_rational(value[1])


def decode_v1(raw: bytes) -> V1StationPiece:
    if not isinstance(raw, bytes):
        raise ValueError('station piece must be supplied as bytes')
    try:
        body = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as error:
        raise ValueError('invalid V1 station piece encoding') from error
    if not isinstance(body, dict) or set(body) != _FIELDS:
        raise ValueError('invalid V1 station piece fields')
    if type(body['version']) is not int or body['version'] != 1:
        raise ValueError('unsupported station piece version')
    if not isinstance(body['nodes'], list):
        raise ValueError('station piece nodes must be a list')
    identities = {field: body[field] for field in _ID_FIELDS}
    return V1StationPiece(
        **identities,
        unit=body['unit'],
        limits=ThicknessLimits(*_rational_pair(body['limits'])),
        curve=NominalCurve(tuple(CurveNode(*_rational_pair(node)) for node in body['nodes'])),
    )


def decode_station_piece(raw: bytes) -> V1StationPiece | V2StationPiece:
    """Decode either a V1 or a V2 station piece, rejecting anything else."""
    if not isinstance(raw, bytes):
        raise ValueError('station piece must be supplied as bytes')
    try:
        version = json.loads(raw.decode('utf-8')).get('version')
    except (ValueError, AttributeError, RecursionError) as error:
        raise ValueError('invalid station piece encoding') from error
    if type(version) is not int or version not in (1, 2):
        raise ValueError('unsupported station piece version')
    return decode_v1(raw) if version == 1 else decode_v2(raw)
