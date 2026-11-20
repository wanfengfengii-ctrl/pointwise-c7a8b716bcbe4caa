from fractions import Fraction
import json
import sqlite3

from application.review import lookup_correction, sign_correction, sign_review
from application.samples import ReviewBatch, SampleInput
from archive.history import retrieve_correction
from examples.correction_fixture import POINT_OVERLAP, TRIANGLE_AND_GAP, seed_case
from release.admission import admit_station_piece
from release.hull import build_hull
from release.issue import issue_v1_station_piece, issue_v2_station_piece
from release.v2_codec import decode_v2
from tests.fixtures import (
    LabTestCase, archive_snapshot, arm_correction_commit_failure,
    disarm_correction_commit_failure,
)


def _states(body):
    return [(segment[0], segment[1], segment[2], segment[3], segment[4])
            for segment in body['segments']]


class CorrectionSigningTests(LabTestCase):
    def accept_v2(self, case):
        _, _, freeze_id = seed_case(self.protocols, self.ledger, case)
        raw = issue_v2_station_piece(self.ledger, self.protocols, freeze_id)
        return admit_station_piece(self.inventory, raw), decode_v2(raw)

    def test_point_overlap_partition(self):
        acceptance_id, piece = self.accept_v2(POINT_OVERLAP)
        self.source.close()
        body, receipt = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 1), (0, 3), Fraction(1, 2),
        )
        self.assertEqual(_states(body), [
            ('0', '0', True, True, 'uncorrectable'),
            ('0', '1', False, False, 'correctable'),
            ('1', '1', True, True, 'correctable'),
        ])
        self.assertEqual(lookup_correction(body, 0), ('uncorrectable', None))
        for reading in (Fraction(1, 3), Fraction(1, 2), Fraction(99, 100), Fraction(1)):
            state, correction = lookup_correction(body, reading)
            self.assertEqual(state, 'correctable')
            self.assertEqual(correction, Fraction(3, 2))
        self.assertEqual(body['provenance']['acceptance_id'], acceptance_id)
        self.assertEqual(body['provenance']['issuance_id'], piece.issuance_id)
        self.assertEqual(set(body['provenance']), {
            'acceptance_id', 'issuance_id', 'fixture_id', 'protocol_id', 'freeze_id', 'revision_id',
        })
        self.assertTrue(receipt.receipt_id)
        # The body is JSON-ready and keeps rational strings and boolean flags.
        encoded = json.dumps(body)
        self.assertEqual(json.loads(encoded), body)

    def test_tolerance_one_pins_zero_to_one(self):
        acceptance_id, _ = self.accept_v2(POINT_OVERLAP)
        body, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 1), (0, 3), Fraction(1),
        )
        self.assertEqual(lookup_correction(body, 0), ('correctable', Fraction(1)))

    def test_triangle_and_gap_partition(self):
        acceptance_id, _ = self.accept_v2(TRIANGLE_AND_GAP)
        body, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 5), (0, 3), Fraction(1, 2),
        )
        self.assertEqual(_states(body), [
            ('0', '0', True, True, 'uncorrectable'),
            ('0', '1', False, False, 'uncorrectable'),
            ('1', '1', True, True, 'correctable'),
            ('1', '2', False, False, 'correctable'),
            ('2', '2', True, True, 'correctable'),
            ('2', '4', False, False, 'no_evidence'),
            ('4', '4', True, True, 'correctable'),
            ('4', '5', False, False, 'no_evidence'),
            ('5', '5', True, True, 'no_evidence'),
        ])
        self.assertEqual(lookup_correction(body, 1), ('correctable', Fraction(3, 2)))
        self.assertEqual(lookup_correction(body, Fraction(3)), ('no_evidence', None))

    def test_singleton_window_limit_behavior(self):
        acceptance_id, _ = self.accept_v2(TRIANGLE_AND_GAP)
        blocked, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (4, 4), (0, 1), Fraction(1, 2),
        )
        self.assertEqual(lookup_correction(blocked, 4), ('uncorrectable', None))
        pinned, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (4, 4), (2, 2), Fraction(1, 2),
        )
        self.assertEqual(lookup_correction(pinned, 4), ('correctable', Fraction(2)))

    def test_equal_endpoint_windows_and_zero_tolerance(self):
        acceptance_id, _ = self.accept_v2(POINT_OVERLAP)
        body, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (1, 1), (0, 3), Fraction(0),
        )
        # At reading 1 only the hot hull supports bias 2, so the exact
        # zero-tolerance correction is the bias itself.
        self.assertEqual(lookup_correction(body, 1), ('correctable', Fraction(2)))
        zero_tol, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 1), (0, 3), Fraction(0),
        )
        self.assertEqual(lookup_correction(zero_tol, 0), ('uncorrectable', None))

    def test_instructions_respect_limits_and_residuals_everywhere(self):
        acceptance_id, piece = self.accept_v2(TRIANGLE_AND_GAP)
        limits = (Fraction(0), Fraction(3))
        tolerance = Fraction(1, 2)
        body, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 5), limits, tolerance,
        )
        hulls = tuple(build_hull(group.vertices) for group in piece.evidence)
        for index in range(601):
            reading = Fraction(index, 120)  # dense grid through [0, 5]
            state, correction = lookup_correction(body, reading)
            supported = tuple(hull for hull in hulls if hull.supports(reading))
            if not supported:
                self.assertEqual(state, 'no_evidence')
                continue
            if state == 'uncorrectable':
                continue
            self.assertGreaterEqual(correction, limits[0])
            self.assertLessEqual(correction, limits[1])
            for hull in supported:
                bias_low, bias_high = hull.bias_interval(reading)
                self.assertLessEqual(abs(bias_low - correction), tolerance)
                self.assertLessEqual(abs(bias_high - correction), tolerance)

    def test_version_mixing_is_rejected(self):
        _, _, freeze_id = seed_case(self.protocols, self.ledger, POINT_OVERLAP)
        v2_raw = issue_v2_station_piece(self.ledger, self.protocols, freeze_id)
        v2_id = admit_station_piece(self.inventory, v2_raw)
        v1_raw = issue_v1_station_piece(self.ledger, self.protocols, freeze_id, 'cold')
        v1_id = admit_station_piece(self.inventory, v1_raw)
        batch = ReviewBatch(v2_id, 'film-bench-a', (SampleInput('strip', 0, 10),))
        with self.assertRaises(ValueError):
            sign_review(self.inventory, self.storage, batch)
        with self.assertRaises(ValueError):
            sign_correction(self.inventory, self.storage, v1_id, (0, 1), (0, 3), Fraction(1, 2))

    def test_invalid_requests(self):
        acceptance_id, _ = self.accept_v2(POINT_OVERLAP)
        with self.assertRaises(KeyError):
            sign_correction(self.inventory, self.storage, 'unknown-acceptance', (0, 1), (0, 3), 0)
        invalid_requests = (
            ((1, 0), (0, 3), 0),
            ((0, 1), (3, 0), 0),
            ((0, 1), (0, 3), -1),
            ((0, 1), (0, 3), 0.5),
            (('x', 1), (0, 3), 0),
            ((0, 1), (0, False), 0),
        )
        for window, limits, tolerance in invalid_requests:
            with self.subTest(window=window, limits=limits, tolerance=tolerance):
                with self.assertRaises(ValueError):
                    sign_correction(
                        self.inventory, self.storage, acceptance_id, window, limits, tolerance,
                    )
        body, _ = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 1), (0, 3), Fraction(1, 2),
        )
        with self.assertRaises(ValueError):
            lookup_correction(body, Fraction(2))
        with self.assertRaises(ValueError):
            lookup_correction(body, '1/0')
        with self.assertRaises(ValueError):
            lookup_correction({}, 0)


class CorrectionHistoryTests(LabTestCase):
    def test_reopen_retrieves_fixed_body_and_receipt(self):
        _, _, freeze_id = seed_case(self.protocols, self.ledger, TRIANGLE_AND_GAP)
        raw = issue_v2_station_piece(self.ledger, self.protocols, freeze_id)
        acceptance_id = admit_station_piece(self.inventory, raw)
        self.source.close()
        body, receipt = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 5), (0, 3), Fraction(1, 2),
        )
        self.app.close()
        self.open_application()
        reloaded_body, reloaded_receipt = retrieve_correction(self.storage, body['report_id'])
        self.assertEqual(reloaded_body, body)
        self.assertEqual(reloaded_receipt, receipt)
        with self.assertRaises(KeyError):
            retrieve_correction(self.storage, 'unknown-report')

    def test_failed_commit_leaves_no_correction_and_retries(self):
        _, _, freeze_id = seed_case(self.protocols, self.ledger, POINT_OVERLAP)
        acceptance_id = admit_station_piece(
            self.inventory, issue_v2_station_piece(self.ledger, self.protocols, freeze_id),
        )
        existing, existing_receipt = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 1), (0, 3), Fraction(1, 2),
        )
        before = archive_snapshot(self.app)
        arm_correction_commit_failure(self.app)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                sign_correction(
                    self.inventory, self.storage, acceptance_id, (0, 1), (0, 3), Fraction(1, 2),
                )
        finally:
            disarm_correction_commit_failure(self.app)
        self.assertFalse(self.app.in_transaction)
        self.app.close()
        self.open_application()
        self.assertEqual(archive_snapshot(self.app), before)
        body, receipt = sign_correction(
            self.inventory, self.storage, acceptance_id, (0, 1), (0, 3), Fraction(1, 2),
        )
        self.assertNotEqual(body['report_id'], existing['report_id'])
        self.assertEqual(retrieve_correction(self.storage, existing['report_id']),
                         (existing, existing_receipt))
        self.assertEqual(retrieve_correction(self.storage, body['report_id']), (body, receipt))
