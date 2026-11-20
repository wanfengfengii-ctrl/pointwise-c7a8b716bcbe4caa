from dataclasses import dataclass

from archive.correction_reports import (
    read_correction_report, validate_correction_provenance,
)
from archive.provenance import ReviewProvenance, validate_provenance
from archive.receipts import SignatureReceipt, read_correction_receipt, read_receipt
from archive.reports import ReviewReport, read_report
from archive.storage import ArchiveStorage


@dataclass(frozen=True)
class ReportHistoryEntry:
    report: ReviewReport
    receipt: SignatureReceipt

    @property
    def provenance(self) -> ReviewProvenance:
        return self.report.provenance


def retrieve_report(storage: ArchiveStorage, report_id: str) -> ReportHistoryEntry:
    report = read_report(storage, report_id)
    receipt = read_receipt(storage.connection, report_id)
    validate_provenance(report.provenance)
    if receipt.report_id != report.report_id:
        raise ValueError('signature receipt belongs to a different report')
    return ReportHistoryEntry(report, receipt)


def retrieve_correction(
    storage: ArchiveStorage, report_id: str
) -> tuple[dict, SignatureReceipt]:
    """Return the fixed (body, receipt) pair for a signed correction table."""
    body, original_bytes = read_correction_report(storage, report_id)
    receipt = read_correction_receipt(storage.connection, report_id)
    validate_correction_provenance(body['provenance'], original_bytes)
    if receipt.report_id != body['report_id']:
        raise ValueError('signature receipt belongs to a different report')
    return body, receipt
