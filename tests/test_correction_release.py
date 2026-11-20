from fractions import Fraction
import json

from application.review import lookup_correction, sign_correction
from archive.history import retrieve_correction
from examples.correction_fixture import POINT_OVERLAP, TRIANGLE_AND_GAP, seed_case
from release.admission import admit_station_piece, get_accepted_piece
from release.hull import Point, build_hull
from release.issue import issue_v1_station_piece, issue_v2_station_piece
from release.v2_codec import decode_v2
from tests.fixtures import LabTestCase


class CorrectionIssueTests(LabTestCase):
    def test_v2_uses_every_registered_group_and_is_deterministic(self):
        _, revision_id, freeze_id = seed_case(self.protocols, self.ledger, POINT_OVERLAP)
        raw = issue_v2_station_piece(self.ledger, self.protocols, freeze_id)
        self.assertEqual(issue_v2_station_piece(self.ledger, self.protocols, freeze_id), raw)
        piece = decode_v2(raw)
        self.assertEqual(piece.version if hasattr(piece, 'version') else 2, 2)
        self.assertEqual((piece.freeze_id, piece.revision_id), (freeze_id, revision_id))
        self.assertEqual([group.group_id for group in piece.evidence], ['cold', 'hot'])
        self.assertEqual(piece.evidence[0].vertices, (Point(0, 0),))
        # Original three-channel rows and trial ids never leave the source ledger.
        self.assertNotIn(b'cold-zero', raw)
        self.assertNotIn(b'hot-one', raw)
        self.assertNotIn(b'reference_head', raw)
        # V1 and V2 issuance identities stay distinct.
        v1_raw = issue_v1_station_piece(self.ledger, self.protocols, freeze_id, 'cold')
        self.assertNotEqual(json.loads(v1_raw)['issuance_id'], piece.issuance_id)

    def test_v2_requires_a_group(self):
        protocol_id, revision_id, freeze_id = self.seed(
            rows=(), groups=(),
        )
        with self.assertRaises(ValueError):
            issue_v2_station_piece(self.ledger, self.protocols, freeze_id)
        with self.assertRaises(KeyError):
            issue_v2_station_piece(self.ledger, self.protocols, 'missing-freeze')

    def test_v2_keeps_vertical_sections_and_triangle(self):
        _, _, freeze_id = seed_case(self.protocols, self.ledger, TRIANGLE_AND_GAP)
        raw = issue_v2_station_piece(self.ledger, self.protocols, freeze_id)
        piece = decode_v2(raw)
        triangle = next(group for group in piece.evidence if group.group_id == 'triangle')
        hull = build_hull(triangle.vertices)
        self.assertEqual(hull.bias_interval(Fraction(0)), (Fraction(0), Fraction(2)))
        self.assertEqual(hull.bias_interval(Fraction(2)), (Fraction(2), Fraction(2)))


class CorrectionAdmissionTests(LabTestCase):
    def _issue_v2(self, case=POINT_OVERLAP):
        _, _, freeze_id = seed_case(self.protocols, self.ledger, case)
        return issue_v2_station_piece(self.ledger, self.protocols, freeze_id)

    def test_admit_replay_conflict_and_reread(self):
        raw = self._issue_v2()
        acceptance_id = admit_station_piece(self.inventory, raw)
        self.assertEqual(admit_station_piece(self.inventory, raw), acceptance_id)
        accepted = get_accepted_piece(self.inventory, acceptance_id)
        self.assertEqual(accepted.original_bytes, raw)
        self.assertEqual(decode_v2(accepted.original_bytes), accepted.piece)

        body = json.loads(raw)
        tampered = json.dumps({**body, 'fixture_id': 'other-bench'}).encode('utf-8')
        with self.assertRaises(ValueError):
            admit_station_piece(self.inventory, tampered)
        with self.assertRaises(ValueError):
            admit_station_piece(self.inventory, b'\n' + raw)
        self.assertEqual(self.app.execute('SELECT COUNT(*) FROM accepted_pieces').fetchone()[0], 1)

    def test_bad_v2_pieces_are_rejected(self):
        raw = self._issue_v2()
        body = json.loads(raw)
        variants = [b'{bad', b'\xff', b'[]', b'{"version":2,"version":2}']
        changes = (
            {'version': 1}, {'version': 3}, {'version': True}, {'fixture_id': ''},
            {'limits': ['10', '9']}, {'evidence': []},
            {'evidence': [{'group_id': 'cold'}]},
            {'evidence': [{'group_id': 'cold', 'vertices': []}]},
            {'evidence': [{'group_id': 'cold', 'vertices': [['0', '1/0']]}]},
            {'evidence': [{'group_id': 'cold', 'vertices': [[0, 1]]}]},
        )
        variants.extend(json.dumps({**body, **change}).encode('utf-8') for change in changes)
        for invalid in variants:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    admit_station_piece(self.inventory, invalid)
        self.assertEqual(self.app.execute('SELECT COUNT(*) FROM accepted_pieces').fetchone()[0], 0)
