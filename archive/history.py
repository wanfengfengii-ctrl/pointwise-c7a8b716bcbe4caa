from dataclasses import dataclass

from archive.provenance import ReviewProvenance, validate_provenance
from archive.receipts import SignatureReceipt, read_receipt
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
