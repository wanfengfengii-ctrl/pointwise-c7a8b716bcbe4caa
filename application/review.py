from application.disposition import evaluate_sample
from application.samples import ReviewBatch, validate_review_batch
from archive.provenance import capture_provenance
from archive.receipts import SignatureReceipt
from archive.reports import ReviewReport, publish_report
from archive.storage import ArchiveStorage
from release.admission import get_accepted_piece
from release.inventory import AdmissionInventory


def sign_review(
    inventory: AdmissionInventory, storage: ArchiveStorage, batch: ReviewBatch
) -> tuple[ReviewReport, SignatureReceipt]:
    if not isinstance(batch, ReviewBatch):
        raise ValueError('expected a review batch')
    accepted = get_accepted_piece(inventory, batch.acceptance_id)
    piece = accepted.piece
    samples = validate_review_batch(batch, piece.fixture_id)
    results = tuple(evaluate_sample(sample, piece.curve, piece.limits) for sample in samples)
    return publish_report(storage, samples, results, capture_provenance(accepted))
