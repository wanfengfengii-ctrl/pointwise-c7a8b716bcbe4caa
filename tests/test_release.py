from fractions import Fraction
import json

from examples.demo import load_example
from measurement.amendments import amend_trial_row
from measurement.freezes import freeze_revision, get_frozen_calibration, read_frozen_group
from measurement.groups import TrialGroup
from measurement.rows import TrialRow
from release.admission import admit_station_piece, get_accepted_piece
from release.issue import issue_v1_station_piece
from tests.fixtures import LabTestCase


class ReleaseTests(LabTestCase):
    def test_accept_frozen_curve(self):
        protocol_id, revision, freeze_id = self.seed()
        amended = amend_trial_row(self.ledger, self.protocols, revision, 'ref-two',
                                  TrialRow('ref-two', 'μm', 2, 0, 2))
        new_freeze = freeze_revision(self.ledger, amended)
        old_id, raw = self.accept(freeze_id)
        self.assertEqual(issue_v1_station_piece(self.ledger, self.protocols, freeze_id, 'steady'), raw)
        other_id, _ = self.accept(freeze_id, 'spare')
        new_id, _ = self.accept(new_freeze)
        self.source.close()
        accepted = get_accepted_piece(self.inventory, old_id)
        piece = accepted.piece
        self.assertEqual(accepted.original_bytes, raw)
        self.assertEqual((piece.fixture_id, piece.protocol_id, piece.freeze_id, piece.revision_id,
                          piece.group_id, piece.unit),
                         ('film-bench-a', protocol_id, freeze_id, revision, 'steady', 'μm'))
        self.assertEqual((piece.limits.lower, piece.limits.upper), (Fraction(19, 2), Fraction(10)))
        expected_nodes = load_example('expected.json')['nodes']
        self.assertEqual([[node.reading, node.bias] for node in piece.curve.nodes],
                         [[Fraction(value) for value in node] for node in expected_nodes])
        spare, = get_accepted_piece(self.inventory, other_id).piece.curve.nodes
        self.assertEqual((spare.reading, spare.bias), (Fraction(9), Fraction(1)))
        new_piece = get_accepted_piece(self.inventory, new_id).piece
        self.assertEqual((new_piece.freeze_id, new_piece.curve.nodes[-1].bias), (new_freeze, Fraction(2)))
        self.assertEqual(len({old_id, new_id, other_id}), 3)
        self.assertNotIn(b'ref-zero', raw)
        self.assertNotIn(b'ref-two', raw)

    def test_equal_duplicates(self):
        rows = (TrialRow('a', 'μm', 0, 0, 0), TrialRow('b', 'μm', 1, 1, 1),
                TrialRow('c', 'μm', 4, 2, 3))
        _, _, freeze_id = self.seed(rows=rows, groups=(TrialGroup('steady', ('c', 'a', 'b')),))
        acceptance_id, _ = self.accept(freeze_id)
        nodes = get_accepted_piece(self.inventory, acceptance_id).piece.curve.nodes
        self.assertEqual([(node.reading, node.bias) for node in nodes], [(0, 0), (2, 1)])

    def test_single_node(self):
        _, _, freeze_id = self.seed(rows=(TrialRow('one', 'μm', 4, 2, 3),),
                                     groups=(TrialGroup('steady', ('one',)),))
        acceptance_id, _ = self.accept(freeze_id)
        self.source.close()
        node, = get_accepted_piece(self.inventory, acceptance_id).piece.curve.nodes
        self.assertEqual((node.reading, node.bias), (Fraction(2), Fraction(1)))

    def test_reject_multivalued_curve(self):
        rows = (TrialRow('low', 'μm', 0, 0, 0), TrialRow('high', 'μm', 0, 0, 2))
        _, revision_id, freeze_id = self.seed(rows=rows, groups=(TrialGroup('steady', ('low', 'high')),))
        with self.assertRaises(ValueError):
            issue_v1_station_piece(self.ledger, self.protocols, freeze_id, 'steady')
        frozen = get_frozen_calibration(self.ledger, freeze_id)
        self.assertEqual(frozen.revision.revision_id, revision_id)
        self.assertEqual(read_frozen_group(frozen, 'steady'), rows)
        with self.assertRaises(KeyError):
            issue_v1_station_piece(self.ledger, self.protocols, 'missing-freeze', 'steady')
        with self.assertRaises(KeyError):
            issue_v1_station_piece(self.ledger, self.protocols, freeze_id, 'missing-group')

    def test_replay_and_conflict(self):
        _, _, freeze_id = self.seed()
        acceptance_id, raw = self.accept(freeze_id)
        self.assertEqual(admit_station_piece(self.inventory, raw), acceptance_id)
        revised_body = json.loads(raw)
        revised_body['nodes'][-1][1] = '2'
        different_body = json.dumps(revised_body).encode('utf-8')
        different_bytes = b'\n' + raw
        self.assertEqual(json.loads(different_bytes), json.loads(raw))
        for conflict in (different_body, different_bytes):
            with self.subTest(conflict=conflict):
                with self.assertRaisesRegex(ValueError, 'conflicting station piece'):
                    admit_station_piece(self.inventory, conflict)
        self.app.close()
        self.open_application()
        self.assertEqual(get_accepted_piece(self.inventory, acceptance_id).original_bytes, raw)
        self.assertEqual(admit_station_piece(self.inventory, raw), acceptance_id)
        self.assertEqual(self.app.execute('SELECT COUNT(*) FROM accepted_pieces').fetchone()[0], 1)

    def test_bad_piece(self):
        _, _, freeze_id = self.seed()
        raw = issue_v1_station_piece(self.ledger, self.protocols, freeze_id, 'steady')
        body = json.loads(raw)
        variants = [b'{bad', b'\xff', b'[]', b'{"version":1,"version":1}']
        changes = (
            {'version': 2}, {'version': True}, {'fixture_id': ''}, {'limits': ['10', '9']},
            {'nodes': []}, {'nodes': [['0', '0'], ['0', '1']]}, {'nodes': [['0', '1/0']]},
            {'nodes': [[0, '1']]},
        )
        variants.extend(json.dumps({**body, **change}).encode('utf-8') for change in changes)
        for invalid in variants:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    admit_station_piece(self.inventory, invalid)
        self.assertEqual(self.app.execute('SELECT COUNT(*) FROM accepted_pieces').fetchone()[0], 0)
