from dataclasses import dataclass
import sqlite3
from uuid import uuid4

from protocol.fixtures import validate_identifier
from release.codec import V1StationPiece, decode_v1


@dataclass(frozen=True)
class AcceptedPiece:
    acceptance_id: str
    original_bytes: bytes
    piece: V1StationPiece


class AdmissionInventory:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS accepted_pieces (
                acceptance_id TEXT PRIMARY KEY NOT NULL,
                issuance_id TEXT NOT NULL UNIQUE,
                original_bytes BLOB NOT NULL
            )
        ''')

    def claim(self, issuance_id: str, original_bytes: bytes) -> str:
        self.connection.execute('BEGIN IMMEDIATE')
        with self.connection:
            self.connection.execute('''
                INSERT INTO accepted_pieces VALUES (?, ?, ?)
                ON CONFLICT(issuance_id) DO NOTHING
            ''', (uuid4().hex, issuance_id, original_bytes))
            acceptance_id, first_bytes = self.connection.execute('''
                SELECT acceptance_id, original_bytes FROM accepted_pieces WHERE issuance_id = ?
            ''', (issuance_id,)).fetchone()
            if first_bytes != original_bytes:
                raise ValueError(f'conflicting station piece for issuance {issuance_id!r}')
        return acceptance_id

    def get(self, acceptance_id: str) -> AcceptedPiece:
        validate_identifier(acceptance_id, 'acceptance id')
        row = self.connection.execute('''
            SELECT issuance_id, original_bytes FROM accepted_pieces WHERE acceptance_id = ?
        ''', (acceptance_id,)).fetchone()
        if row is None:
            raise KeyError(acceptance_id)
        issuance_id, raw = row
        piece = decode_v1(raw)
        if piece.issuance_id != issuance_id:
            raise ValueError('stored issuance identity does not match the station piece')
        return AcceptedPiece(acceptance_id, raw, piece)
