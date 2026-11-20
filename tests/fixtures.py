from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from examples.demo import initialize_application, initialize_source, seed_calibration
from release.admission import admit_station_piece
from release.issue import issue_v1_station_piece


class LabTestCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='film-regression-')
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.source_path = root / 'calibration.sqlite3'
        self.app_path = root / 'application.sqlite3'
        self.open_source()
        self.open_application()

    def open_source(self):
        self.source = sqlite3.connect(self.source_path)
        self.addCleanup(self.source.close)
        self.protocols, self.ledger = initialize_source(self.source)

    def open_application(self):
        self.app = sqlite3.connect(self.app_path)
        self.addCleanup(self.app.close)
        self.inventory, self.storage = initialize_application(self.app)

    def seed(self, **options):
        return seed_calibration(self.protocols, self.ledger, **options)

    def accept(self, freeze_id, group_id='steady'):
        raw = issue_v1_station_piece(self.ledger, self.protocols, freeze_id, group_id)
        return admit_station_piece(self.inventory, raw), raw

    def accept_offline(self, **options):
        _, _, frozen = self.seed(**options)
        acceptance_id, _ = self.accept(frozen)
        self.source.close()
        return acceptance_id


def archive_snapshot(connection):
    reports = connection.execute('SELECT * FROM review_reports ORDER BY report_id').fetchall()
    receipts = connection.execute('SELECT * FROM review_receipts ORDER BY report_id').fetchall()
    correction_reports = connection.execute(
        'SELECT * FROM correction_reports ORDER BY report_id'
    ).fetchall()
    correction_receipts = connection.execute(
        'SELECT * FROM correction_receipts ORDER BY report_id'
    ).fetchall()
    return reports, receipts, correction_reports, correction_receipts


def arm_commit_failure(connection):
    connection.executescript('''
        CREATE TABLE test_receipt_parent (id TEXT PRIMARY KEY);
        CREATE TABLE test_receipt_guard (
            id TEXT REFERENCES test_receipt_parent(id) DEFERRABLE INITIALLY DEFERRED
        );
        CREATE TRIGGER test_guard_new_receipt AFTER INSERT ON review_receipts
        BEGIN
            INSERT INTO test_receipt_guard VALUES (NEW.receipt_id);
        END;
    ''')


def disarm_commit_failure(connection):
    connection.executescript('''
        DROP TRIGGER test_guard_new_receipt;
        DROP TABLE test_receipt_guard;
        DROP TABLE test_receipt_parent;
    ''')


def arm_correction_commit_failure(connection):
    connection.executescript('''
        CREATE TABLE test_correction_parent (id TEXT PRIMARY KEY);
        CREATE TABLE test_correction_guard (
            id TEXT REFERENCES test_correction_parent(id) DEFERRABLE INITIALLY DEFERRED
        );
        CREATE TRIGGER test_guard_new_correction AFTER INSERT ON correction_receipts
        BEGIN
            INSERT INTO test_correction_guard VALUES (NEW.receipt_id);
        END;
    ''')


def disarm_correction_commit_failure(connection):
    connection.executescript('''
        DROP TRIGGER test_guard_new_correction;
        DROP TABLE test_correction_guard;
        DROP TABLE test_correction_parent;
    ''')
