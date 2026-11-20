from dataclasses import dataclass
import sqlite3
from uuid import uuid4

from protocol.fixtures import validate_identifier


@dataclass(frozen=True)
class SignatureReceipt:
    report_id: str
    receipt_id: str


def write_receipt(connection: sqlite3.Connection, report_id: str) -> SignatureReceipt:
    validate_identifier(report_id, 'report id')
    if not connection.in_transaction:
        raise sqlite3.ProgrammingError('receipt writes require an active report transaction')
    receipt = SignatureReceipt(report_id, uuid4().hex)
    connection.execute(
        'INSERT INTO review_receipts VALUES (?, ?)', (receipt.report_id, receipt.receipt_id)
    )
    return receipt


def read_receipt(connection: sqlite3.Connection, report_id: str) -> SignatureReceipt:
    validate_identifier(report_id, 'report id')
    row = connection.execute(
        'SELECT report_id, receipt_id FROM review_receipts WHERE report_id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise KeyError(report_id)
    return SignatureReceipt(*row)
