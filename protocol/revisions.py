from dataclasses import dataclass
import json
import sqlite3
from uuid import uuid4

from protocol.fixtures import Fixture, validate_identifier
from protocol.gauges import GaugeSpec
from protocol.limits import ThicknessLimits
from protocol.quantities import UnitConversion, format_rational


@dataclass(frozen=True)
class ProtocolRevision:
    protocol_id: str
    fixture: Fixture
    gauge: GaugeSpec
    conversion: UnitConversion
    limits: ThicknessLimits


class ProtocolStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS protocol_revisions (
                protocol_id TEXT PRIMARY KEY NOT NULL,
                specification TEXT NOT NULL
            )
        ''')

    def register(
        self,
        fixture: Fixture,
        gauge: GaugeSpec,
        conversion: UnitConversion,
        limits: ThicknessLimits,
    ) -> str:
        if not isinstance(gauge, GaugeSpec):
            raise ValueError('a gauge specification is required')
        gauge.require_compatible(fixture)
        if not isinstance(conversion, UnitConversion) or not isinstance(limits, ThicknessLimits):
            raise ValueError('unit conversion and thickness limits are required')

        protocol_id = uuid4().hex
        specification = {
            'fixture_id': fixture.fixture_id,
            'gauge_id': gauge.gauge_id,
            'gauge_fixtures': gauge.fixture_ids,
            'unit': conversion.unit,
            'multiplier': format_rational(conversion.multiplier),
            'limits': [format_rational(limits.lower), format_rational(limits.upper)],
        }
        with self.connection:
            self.connection.execute(
                'INSERT INTO protocol_revisions VALUES (?, ?)',
                (protocol_id, json.dumps(specification)),
            )
        return protocol_id

    def get(self, protocol_id: str) -> ProtocolRevision:
        validate_identifier(protocol_id, 'protocol id')
        row = self.connection.execute(
            'SELECT specification FROM protocol_revisions WHERE protocol_id = ?',
            (protocol_id,),
        ).fetchone()
        if row is None:
            raise KeyError(protocol_id)
        specification = json.loads(row[0])
        return ProtocolRevision(
            protocol_id,
            Fixture(specification['fixture_id']),
            GaugeSpec(specification['gauge_id'], tuple(specification['gauge_fixtures'])),
            UnitConversion(specification['unit'], specification['multiplier']),
            ThicknessLimits(*specification['limits']),
        )
