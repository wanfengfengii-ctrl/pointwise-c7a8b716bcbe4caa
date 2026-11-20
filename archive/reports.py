from dataclasses import asdict, dataclass
from fractions import Fraction
import json
from uuid import uuid4

from application.disposition import Disposition, SampleResult
from application.samples import ValidatedSample
from archive.provenance import ReviewProvenance, validate_provenance
from archive.receipts import SignatureReceipt, write_receipt
from archive.storage import ArchiveStorage
from protocol.fixtures import validate_identifier
from protocol.quantities import format_rational, parse_rational


@dataclass(frozen=True)
class ReviewReport:
    report_id: str
    samples: tuple[ValidatedSample, ...]
    results: tuple[SampleResult, ...]
    provenance: ReviewProvenance


def _optional_text(value: Fraction | None) -> str | None:
    return None if value is None else format_rational(value)


def _optional_rational(value: str | None) -> Fraction | None:
    return None if value is None else parse_rational(value)


def _encode_body(report: ReviewReport) -> str:
    provenance = asdict(report.provenance)
    del provenance['original_bytes']
    return json.dumps({
        'samples': [
            [sample.sample_id, format_rational(sample.reference), _optional_text(sample.thickness)]
            for sample in report.samples
        ],
        'results': [
            [result.sample_id, result.disposition.value, _optional_text(result.bias),
             _optional_text(result.corrected_thickness)]
            for result in report.results
        ],
        'provenance': provenance,
    }, sort_keys=True, separators=(',', ':'))


def publish_report(
    storage: ArchiveStorage,
    samples: tuple[ValidatedSample, ...],
    results: tuple[SampleResult, ...],
    provenance: ReviewProvenance,
) -> tuple[ReviewReport, SignatureReceipt]:
    samples = tuple(samples)
    results = tuple(results)
    if not samples or tuple(sample.sample_id for sample in samples) != tuple(
        result.sample_id for result in results
    ):
        raise ValueError('report results must correspond to the batch in input order')
    validate_provenance(provenance)
    report = ReviewReport(uuid4().hex, samples, results, provenance)
    body = _encode_body(report)
    with storage.transaction() as connection:
        connection.execute(
            'INSERT INTO review_reports VALUES (?, ?, ?)',
            (report.report_id, body, provenance.original_bytes),
        )
        receipt = write_receipt(connection, report.report_id)
    return report, receipt


def read_report(storage: ArchiveStorage, report_id: str) -> ReviewReport:
    validate_identifier(report_id, 'report id')
    row = storage.connection.execute(
        'SELECT body, piece_bytes FROM review_reports WHERE report_id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise KeyError(report_id)
    payload, original_bytes = row
    body = json.loads(payload)
    provenance = ReviewProvenance(**body['provenance'], original_bytes=original_bytes)
    return ReviewReport(
        report_id,
        tuple(ValidatedSample(sample_id, parse_rational(reference), _optional_rational(thickness))
              for sample_id, reference, thickness in body['samples']),
        tuple(SampleResult(sample_id, Disposition(disposition), _optional_rational(bias),
                           _optional_rational(corrected))
              for sample_id, disposition, bias, corrected in body['results']),
        provenance,
    )
