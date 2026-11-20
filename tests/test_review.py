from fractions import Fraction
import sqlite3

from application.disposition import Disposition
from application.review import sign_review
from application.samples import ReviewBatch, SampleInput
from archive.history import retrieve_report
from examples.demo import load_example, result_summary, sample_batch
from measurement.groups import TrialGroup
from measurement.rows import TrialRow
from tests.fixtures import LabTestCase, archive_snapshot, arm_commit_failure, disarm_commit_failure


class ReviewTests(LabTestCase):
    def test_interpolate_and_grade(self):
        protocol_id, _, freeze_id = self.seed()
        acceptance_id, raw = self.accept(freeze_id)
        self.source.close()
        report, receipt = sign_review(self.inventory, self.storage, sample_batch(acceptance_id))
        expected = load_example('expected.json')['first']
        self.assertEqual(result_summary(report), expected)
        self.assertEqual(report.results[0].corrected_thickness, Fraction(19, 2))
        self.assertEqual((report.provenance.acceptance_id, report.provenance.protocol_id,
                          report.provenance.freeze_id, report.provenance.original_bytes),
                         (acceptance_id, protocol_id, freeze_id, raw))
        archived = retrieve_report(self.storage, report.report_id)
        self.assertEqual(archived.report, report)
        self.assertEqual(archived.receipt, receipt)

    def test_review_inputs(self):
        acceptance_id = self.accept_offline()
        samples = (SampleInput('good', 1, 10),)
        fixture = 'film-bench-a'
        with self.assertRaises(KeyError):
            sign_review(self.inventory, self.storage, ReviewBatch('unknown', fixture, samples))
        invalid = (
            ReviewBatch(acceptance_id, 'wrong-fixture', samples),
            ReviewBatch(acceptance_id, fixture, ()),
            ReviewBatch(acceptance_id, fixture, samples + samples),
            ReviewBatch(acceptance_id, fixture, samples + (SampleInput('bad-ref', '1/0', None),)),
            ReviewBatch(acceptance_id, fixture, samples + (SampleInput('bad-thickness', 2, 0.2),)),
            ReviewBatch(acceptance_id, fixture, (SampleInput('boolean', 0, False),)),
        )
        for batch in invalid:
            with self.subTest(batch=batch):
                with self.assertRaises(ValueError):
                    sign_review(self.inventory, self.storage, batch)
        self.assertEqual(archive_snapshot(self.app), ([], [], [], []))

    def test_exact_fraction(self):
        acceptance_id = self.accept_offline(
            rows=(TrialRow('a', 'μm', 0, 0, 0), TrialRow('b', 'μm', 2, 0, '2/3')),
            groups=(TrialGroup('steady', ('a', 'b')),),
        )
        report, _ = sign_review(self.inventory, self.storage, sample_batch(acceptance_id))
        actual = retrieve_report(self.storage, report.report_id).report.results[0]
        self.assertEqual(actual.bias, Fraction(1, 3))
        self.assertEqual(actual.corrected_thickness, Fraction(29, 3))
        self.assertEqual(actual.disposition, Disposition.PASS)

    def test_closed_limits(self):
        acceptance_id = self.accept_offline()
        batch = ReviewBatch(acceptance_id, 'film-bench-a', (
            SampleInput('lower', 1, 10), SampleInput('upper', 2, 11),
            SampleInput('beyond', 0, '101/10'),
        ))
        report, _ = sign_review(self.inventory, self.storage, batch)
        self.assertEqual([(entry.sample_id, entry.corrected_thickness, entry.disposition)
                          for entry in report.results], [
            ('lower', Fraction(19, 2), Disposition.PASS),
            ('upper', Fraction(10), Disposition.PASS),
            ('beyond', Fraction(101, 10), Disposition.OUT_OF_LIMITS),
        ])

    def test_missing_zero_and_outside(self):
        acceptance_id = self.accept_offline()
        batch = ReviewBatch(acceptance_id, 'film-bench-a', (
            SampleInput('missing', 3, None), SampleInput('zero', 0, 0), SampleInput('outside', 3, 10),
        ))
        report, _ = sign_review(self.inventory, self.storage, batch)
        self.assertEqual([(item.sample_id, item.thickness) for item in report.samples],
                         [('missing', None), ('zero', Fraction(0)), ('outside', Fraction(10))])
        self.assertEqual([(item.sample_id, item.disposition, item.bias, item.corrected_thickness)
                          for item in report.results], [
            ('missing', Disposition.MISSING, None, None),
            ('zero', Disposition.OUT_OF_LIMITS, Fraction(0), Fraction(0)),
            ('outside', Disposition.OUTSIDE_CURVE, None, None),
        ])
        self.assertEqual(retrieve_report(self.storage, report.report_id).report, report)

    def test_single_node(self):
        acceptance_id = self.accept_offline(
            rows=(TrialRow('one', 'μm', 0, 0, 0),), groups=(TrialGroup('steady', ('one',)),),
        )
        batch = ReviewBatch(acceptance_id, 'film-bench-a', (
            SampleInput('exact', 0, 10), SampleInput('near', '1/999', 10),
        ))
        report, _ = sign_review(self.inventory, self.storage, batch)
        self.assertEqual([(item.disposition, item.corrected_thickness) for item in report.results],
                         [(Disposition.PASS, Fraction(10)), (Disposition.OUTSIDE_CURVE, None)])

    def test_failed_commit_retry(self):
        acceptance_id = self.accept_offline()
        batch = sample_batch(acceptance_id)
        existing, existing_receipt = sign_review(self.inventory, self.storage, batch)
        before = archive_snapshot(self.app)
        arm_commit_failure(self.app)
        trace = []
        self.app.set_trace_callback(trace.append)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                sign_review(self.inventory, self.storage, batch)
        finally:
            self.app.set_trace_callback(None)
        commands = [statement.strip().upper() for statement in trace]
        report_write = next(i for i, command in enumerate(commands) if command.startswith('INSERT INTO REVIEW_REPORTS'))
        receipt_write = next(i for i, command in enumerate(commands) if command.startswith('INSERT INTO REVIEW_RECEIPTS'))
        self.assertLess(report_write, receipt_write)
        self.assertLess(receipt_write, commands.index('COMMIT'))
        self.assertLess(commands.index('COMMIT'), commands.index('ROLLBACK'))
        self.assertFalse(self.app.in_transaction)
        self.app.close()
        self.open_application()
        self.assertEqual(archive_snapshot(self.app), before)
        self.assertEqual(self.app.execute('SELECT COUNT(*) FROM test_receipt_guard').fetchone()[0], 0)
        self.assertEqual(retrieve_report(self.storage, existing.report_id).receipt, existing_receipt)
        disarm_commit_failure(self.app)
        report, receipt = sign_review(self.inventory, self.storage, batch)
        self.assertNotEqual(existing.report_id, report.report_id)
        self.assertEqual(report.results, existing.results)
        reports, receipts, correction_reports, correction_receipts = archive_snapshot(self.app)
        self.assertEqual((len(reports), len(receipts)), (2, 2))
        self.assertEqual((len(correction_reports), len(correction_receipts)), (0, 0))
        retrieved = retrieve_report(self.storage, report.report_id)
        self.assertEqual((retrieved.report, retrieved.receipt), (report, receipt))
