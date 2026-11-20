from dataclasses import dataclass
import json

from protocol.fixtures import validate_fixture_id, validate_identifier
from protocol.limits import ThicknessLimits
from protocol.quantities import CANONICAL_UNIT, format_rational, parse_rational
from release.hull import Point

_ID_FIELDS = ('issuance_id', 'fixture_id', 'protocol_id', 'freeze_id', 'revision_id')
_FIELDS = {*_ID_FIELDS, 'version', 'unit', 'limits', 'evidence'}


@dataclass(frozen=True)
class EvidenceGroup:
    group_id: str
    vertices: tuple[Point, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.group_id, 'group id')
        vertices = tuple(self.vertices)
        if not vertices or any(not isinstance(point, Point) for point in vertices):
            raise ValueError('an evidence group needs at least one hull vertex')
        object.__setattr__(self, 'vertices', vertices)


@dataclass(frozen=True)
class V2StationPiece:
    issuance_id: str
    fixture_id: str
    protocol_id: str
    freeze_id: str
    revision_id: str
    unit: str
    limits: ThicknessLimits
    evidence: tuple[EvidenceGroup, ...]

    def __post_init__(self) -> None:
        validate_fixture_id(self.fixture_id)
        for field in _ID_FIELDS:
            validate_identifier(getattr(self, field), field)
        if self.unit != CANONICAL_UNIT:
            raise ValueError('unexpected station piece unit')
        if not isinstance(self.limits, ThicknessLimits):
            raise ValueError('station piece requires thickness limits')
        evidence = tuple(self.evidence)
        if not evidence or any(not isinstance(group, EvidenceGroup) for group in evidence):
            raise ValueError('a V2 station piece needs at least one evidence group')
        if len({group.group_id for group in evidence}) != len(evidence):
            raise ValueError('duplicate evidence group id')
        object.__setattr__(self, 'evidence', evidence)


def encode_v2(piece: V2StationPiece) -> bytes:
    if not isinstance(piece, V2StationPiece):
        raise ValueError('expected a V2 station piece')
    body = {field: getattr(piece, field) for field in _ID_FIELDS}
    body.update(
        version=2,
        unit=piece.unit,
        limits=[format_rational(piece.limits.lower), format_rational(piece.limits.upper)],
        evidence=[
            {
                'group_id': group.group_id,
                'vertices': [[format_rational(point.x), format_rational(point.y)]
                             for point in sorted(group.vertices, key=lambda point: (point.x, point.y))],
            }
            for group in sorted(piece.evidence, key=lambda group: group.group_id)
        ],
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


def _decode_group(value: object) -> EvidenceGroup:
    if not isinstance(value, dict) or set(value) != {'group_id', 'vertices'}:
        raise ValueError('invalid evidence group structure')
    if type(value['group_id']) is not str:
        raise ValueError('invalid evidence group id')
    vertices = value['vertices']
    if not isinstance(vertices, list) or not vertices:
        raise ValueError('an evidence group needs at least one hull vertex')
    points = tuple(Point(*_rational_pair(vertex)) for vertex in vertices)
    return EvidenceGroup(value['group_id'], points)


def decode_v2(raw: bytes) -> V2StationPiece:
    if not isinstance(raw, bytes):
        raise ValueError('station piece must be supplied as bytes')
    try:
        body = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as error:
        raise ValueError('invalid V2 station piece encoding') from error
    if not isinstance(body, dict) or set(body) != _FIELDS:
        raise ValueError('invalid V2 station piece fields')
    if type(body['version']) is not int or body['version'] != 2:
        raise ValueError('unsupported station piece version')
    if not isinstance(body['evidence'], list) or not body['evidence']:
        raise ValueError('a V2 station piece needs at least one evidence group')
    evidence = tuple(_decode_group(group) for group in body['evidence'])
    if len({group.group_id for group in evidence}) != len(evidence):
        raise ValueError('duplicate evidence group id')
    identities = {field: body[field] for field in _ID_FIELDS}
    return V2StationPiece(
        **identities,
        unit=body['unit'],
        limits=ThicknessLimits(*_rational_pair(body['limits'])),
        evidence=evidence,
    )
