from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3


class ArchiveStorage:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS review_reports (
                report_id TEXT PRIMARY KEY NOT NULL,
                body TEXT NOT NULL,
                piece_bytes BLOB NOT NULL
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS review_receipts (
                report_id TEXT PRIMARY KEY NOT NULL REFERENCES review_reports(report_id),
                receipt_id TEXT NOT NULL UNIQUE
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS correction_reports (
                report_id TEXT PRIMARY KEY NOT NULL,
                body TEXT NOT NULL,
                piece_bytes BLOB NOT NULL
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS correction_receipts (
                report_id TEXT PRIMARY KEY NOT NULL REFERENCES correction_reports(report_id),
                receipt_id TEXT NOT NULL UNIQUE
            )
        ''')

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield self.connection
            self.connection.commit()
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise
