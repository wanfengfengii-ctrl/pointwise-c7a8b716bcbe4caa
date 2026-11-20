from dataclasses import dataclass
import json
import sqlite3
from uuid import uuid4

from measurement.groups import TrialGroup
from measurement.rows import TrialRow
from protocol.fixtures import validate_identifier
from protocol.quantities import format_rational


@dataclass(frozen=True)
class CalibrationRevision:
    revision_id: str
    protocol_id: str
    parent_id: str | None
    rows: tuple[TrialRow, ...]
    groups: tuple[TrialGroup, ...]


@dataclass(frozen=True)
class FrozenCalibration:
    freeze_id: str
    revision: CalibrationRevision


class CalibrationLedger:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS calibration_revisions (
                revision_id TEXT PRIMARY KEY NOT NULL,
                protocol_id TEXT NOT NULL REFERENCES protocol_revisions(protocol_id),
                parent_id TEXT REFERENCES calibration_revisions(revision_id),
                trial_rows TEXT NOT NULL,
                trial_groups TEXT NOT NULL
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS calibration_freezes (
                freeze_id TEXT PRIMARY KEY NOT NULL,
                revision_id TEXT NOT NULL UNIQUE REFERENCES calibration_revisions(revision_id)
            )
        ''')

    def store_revision(
        self,
        protocol_id: str,
        parent_id: str | None,
        rows: tuple[TrialRow, ...],
        groups: tuple[TrialGroup, ...],
    ) -> str:
        revision_id = uuid4().hex
        trial_rows = [
            [row.row_id, row.unit, format_rational(row.reference_head),
             format_rational(row.gauge), format_rational(row.thickness_head)]
            for row in rows
        ]
        trial_groups = [[group.group_id, group.row_ids] for group in groups]
        with self.connection:
            self.connection.execute(
                'INSERT INTO calibration_revisions VALUES (?, ?, ?, ?, ?)',
                (revision_id, protocol_id, parent_id, json.dumps(trial_rows), json.dumps(trial_groups)),
            )
        return revision_id

    def get_revision(self, revision_id: str) -> CalibrationRevision:
        validate_identifier(revision_id, 'calibration revision id')
        row = self.connection.execute('''
            SELECT protocol_id, parent_id, trial_rows, trial_groups
            FROM calibration_revisions WHERE revision_id = ?
        ''', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        protocol_id, parent_id, trial_rows, trial_groups = row
        return CalibrationRevision(
            revision_id,
            protocol_id,
            parent_id,
            tuple(TrialRow(*fields) for fields in json.loads(trial_rows)),
            tuple(TrialGroup(group_id, tuple(row_ids)) for group_id, row_ids in json.loads(trial_groups)),
        )

    def store_freeze(self, revision_id: str) -> str:
        self.get_revision(revision_id)
        with self.connection:
            self.connection.execute('''
                INSERT INTO calibration_freezes VALUES (?, ?)
                ON CONFLICT(revision_id) DO NOTHING
            ''', (uuid4().hex, revision_id))
            row = self.connection.execute(
                'SELECT freeze_id FROM calibration_freezes WHERE revision_id = ?',
                (revision_id,),
            ).fetchone()
        return row[0]

    def get_freeze(self, freeze_id: str) -> FrozenCalibration:
        validate_identifier(freeze_id, 'freeze id')
        row = self.connection.execute(
            'SELECT revision_id FROM calibration_freezes WHERE freeze_id = ?',
            (freeze_id,),
        ).fetchone()
        if row is None:
            raise KeyError(freeze_id)
        return FrozenCalibration(freeze_id, self.get_revision(row[0]))
