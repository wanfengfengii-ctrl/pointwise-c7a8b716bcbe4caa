from application.review import sign_review
from archive.history import retrieve_report
from examples.demo import load_example, result_summary, sample_batch
from measurement.amendments import amend_trial_row
from measurement.freezes import freeze_revision
from measurement.rows import TrialRow
from release.admission import admit_station_piece, get_accepted_piece
from tests.fixtures import LabTestCase


class HistoryTests(LabTestCase):
    def test_reopen_after_source_amendment(self):
        protocol_id, first_revision, first_freeze = self.seed()
        first_id, first_raw = self.accept(first_freeze)
        self.source.close()
        first, first_receipt = sign_review(self.inventory, self.storage, sample_batch(first_id))
        self.open_source()
        amended = amend_trial_row(self.ledger, self.protocols, first_revision, 'ref-two',
                                  TrialRow('ref-two', 'μm', 2, 0, 2))
        second_freeze = freeze_revision(self.ledger, amended)
        second_id, second_raw = self.accept(second_freeze)
        self.source.close()
        second, second_receipt = sign_review(self.inventory, self.storage, sample_batch(second_id))
        self.app.close()
        self.open_application()

        expected = load_example('expected.json')
        old = retrieve_report(self.storage, first.report_id)
        new = retrieve_report(self.storage, second.report_id)
        self.assertEqual((old.report, old.receipt), (first, first_receipt))
        self.assertEqual((new.report, new.receipt), (second, second_receipt))
        self.assertEqual(result_summary(old.report), expected['first'])
        self.assertEqual(result_summary(new.report), expected['after_amendment'])
        self.assertNotEqual(old.receipt.receipt_id, new.receipt.receipt_id)
        self.assertEqual((old.provenance.protocol_id, old.provenance.freeze_id, old.provenance.revision_id,
                          old.provenance.acceptance_id, old.provenance.original_bytes),
                         (protocol_id, first_freeze, first_revision, first_id, first_raw))
        self.assertEqual((new.provenance.protocol_id, new.provenance.freeze_id, new.provenance.revision_id,
                          new.provenance.acceptance_id, new.provenance.original_bytes),
                         (protocol_id, second_freeze, amended, second_id, second_raw))
        with self.assertRaises(KeyError):
            retrieve_report(self.storage, 'unknown-report')

    def test_reinitialize(self):
        _, _, freeze_id = self.seed()
        acceptance_id, raw = self.accept(freeze_id)
        self.source.close()
        report, receipt = sign_review(self.inventory, self.storage, sample_batch(acceptance_id))
        self.inventory.initialize()
        self.storage.initialize()
        self.app.close()
        self.open_application()
        self.assertEqual(admit_station_piece(self.inventory, raw), acceptance_id)
        self.assertEqual(get_accepted_piece(self.inventory, acceptance_id).original_bytes, raw)
        archived = retrieve_report(self.storage, report.report_id)
        self.assertEqual((archived.report, archived.receipt), (report, receipt))
        self.assertEqual(archived.provenance.freeze_id, freeze_id)
