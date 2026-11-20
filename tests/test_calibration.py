from fractions import Fraction

from measurement.amendments import amend_trial_row, submit_trial_revision
from measurement.freezes import freeze_revision, get_frozen_calibration, read_frozen_group
from measurement.groups import TrialGroup
from measurement.rows import TrialRow, normalize_trial_row
from protocol.fixtures import Fixture
from protocol.gauges import GaugeSpec
from protocol.limits import ThicknessLimits
from protocol.quantities import UnitConversion
from tests.fixtures import LabTestCase


class CalibrationTests(LabTestCase):
    def test_freeze_after_amendment(self):
        protocol_id, first_revision, first_freeze = self.seed()
        original = read_frozen_group(get_frozen_calibration(self.ledger, first_freeze), 'steady')
        correction = TrialRow('ref-two', 'μm', 2, 0, '3/2')
        amended = amend_trial_row(self.ledger, self.protocols, first_revision, 'ref-two', correction)
        second_freeze = freeze_revision(self.ledger, amended)
        self.source.close()
        self.open_source()
        before = get_frozen_calibration(self.ledger, first_freeze)
        after = get_frozen_calibration(self.ledger, second_freeze)
        self.assertNotEqual(first_freeze, second_freeze)
        self.assertEqual(before.revision.revision_id, first_revision)
        self.assertEqual(after.revision.revision_id, amended)
        self.assertEqual(after.revision.parent_id, first_revision)
        self.assertEqual((before.revision.protocol_id, after.revision.protocol_id), (protocol_id, protocol_id))
        self.assertEqual(read_frozen_group(before, 'steady'), original)
        self.assertEqual(original[1].thickness_head, Fraction(1))
        self.assertEqual(read_frozen_group(after, 'steady'), (original[0], correction))
        self.assertEqual(freeze_revision(self.ledger, amended), second_freeze)

    def test_protocol_validation(self):
        fixture = Fixture('bench-a')
        wrong_gauge = GaugeSpec('glass-b', ('bench-b',))
        right_gauge = GaugeSpec('glass-a', ('bench-a',))
        unit = UnitConversion('μm', 1)
        with self.assertRaises(ValueError):
            self.protocols.register(fixture, wrong_gauge, unit, ThicknessLimits(9, 10))
        with self.assertRaises(ValueError):
            self.protocols.register(fixture, right_gauge, unit, ThicknessLimits(10, 9))
        self.assertEqual(self.source.execute('SELECT COUNT(*) FROM protocol_revisions').fetchone()[0], 0)
        protocol_id = self.protocols.register(fixture, right_gauge, unit, ThicknessLimits(10, 10))
        found = self.protocols.get(protocol_id)
        self.assertEqual((found.fixture, found.gauge), (fixture, right_gauge))
        self.assertTrue(found.limits.contains(Fraction(10)))
        self.assertFalse(found.limits.contains(Fraction(999, 100)))

    def test_protocol_history(self):
        fixture = Fixture('bench-a')
        gauge = GaugeSpec('glass-a', ('bench-a',))
        old_id = self.protocols.register(fixture, gauge, UnitConversion('mm', 1000), ThicknessLimits(9, 10))
        row = TrialRow('user-row', 'mm', '3/2000', '1/2000', '3/4000')
        revision = submit_trial_revision(self.ledger, self.protocols, old_id, (row,),
                                         (TrialGroup('user-group', ('user-row',)),))
        freeze_id = freeze_revision(self.ledger, revision)
        changed = TrialRow('user-row', 'mm', '3/2000', '1/2000', '7/8000')
        amended = amend_trial_row(self.ledger, self.protocols, revision, 'user-row', changed)
        newer_id = self.protocols.register(fixture, gauge, UnitConversion('μm', 1), ThicknessLimits(8, 11))
        self.protocols.initialize()
        self.ledger.initialize()
        self.source.close()
        self.open_source()
        old = self.protocols.get(old_id)
        newer = self.protocols.get(newer_id)
        self.assertNotEqual(old.protocol_id, newer.protocol_id)
        self.assertEqual((old.conversion.unit, old.limits.lower), ('mm', Fraction(9)))
        self.assertEqual((newer.conversion.unit, newer.limits.upper), ('μm', Fraction(11)))
        frozen = get_frozen_calibration(self.ledger, freeze_id)
        self.assertEqual(frozen.revision.protocol_id, old_id)
        retained, = read_frozen_group(frozen, 'user-group')
        self.assertEqual(retained, row)
        normalized = normalize_trial_row(retained, old.conversion)
        self.assertEqual((normalized.reference_head, normalized.gauge, normalized.thickness_head),
                         (Fraction(3, 2), Fraction(1, 2), Fraction(3, 4)))
        self.assertEqual(self.ledger.get_revision(amended).rows, (changed,))

    def test_unknown_refs(self):
        protocol_id, revision, _ = self.seed()
        with self.assertRaises(KeyError):
            submit_trial_revision(self.ledger, self.protocols, 'unknown-protocol')
        with self.assertRaises(KeyError):
            submit_trial_revision(self.ledger, self.protocols, protocol_id, parent_id='unknown-parent')
        with self.assertRaises(KeyError):
            submit_trial_revision(self.ledger, self.protocols, protocol_id,
                                  groups=(TrialGroup('bad', ('unknown-trial',)),), parent_id=revision)
        with self.assertRaises(KeyError):
            amend_trial_row(self.ledger, self.protocols, revision, 'unknown-trial',
                            TrialRow('unknown-trial', 'μm', 0, 0, 0))
        with self.assertRaises(KeyError):
            freeze_revision(self.ledger, 'unknown-revision')

    def test_reject_invalid_trial_batch(self):
        protocol_id, revision, first_freeze = self.seed()
        good = TrialRow('new-row', 'μm', 4, 0, 1)
        bad_endings = (TrialRow('wrong-unit', 'mm', 3, 0, 1), good, TrialRow('ref-two', 'μm', 2, 0, 1))
        for ending in bad_endings:
            with self.subTest(ending=ending):
                with self.assertRaises(ValueError):
                    submit_trial_revision(self.ledger, self.protocols, protocol_id, (good, ending),
                                          (TrialGroup('new', ('new-row',)),), parent_id=revision)
                self.source.close()
                self.open_source()
                remaining = self.source.execute('SELECT revision_id FROM calibration_revisions').fetchall()
                self.assertEqual(remaining, [(revision,)])
                self.assertEqual(freeze_revision(self.ledger, revision), first_freeze)
                old = get_frozen_calibration(self.ledger, first_freeze)
                self.assertEqual([row.row_id for row in read_frozen_group(old, 'steady')], ['ref-zero', 'ref-two'])

    def test_reject_invalid_group_and_parent_protocol(self):
        protocol_id, revision, _ = self.seed()
        with self.assertRaises(ValueError):
            TrialGroup('empty', ())
        with self.assertRaises(ValueError):
            TrialGroup('duplicate', ('ref-two', 'ref-two'))
        group = TrialGroup('two', ('ref-two',))
        with self.assertRaises(ValueError):
            submit_trial_revision(self.ledger, self.protocols, protocol_id,
                                  groups=(group, group), parent_id=revision)
        other_id = self.protocols.register(Fixture('other'), GaugeSpec('glass-other', ('other',)),
                                           UnitConversion('μm', 1), ThicknessLimits(0, 1))
        with self.assertRaises(ValueError):
            submit_trial_revision(self.ledger, self.protocols, other_id, parent_id=revision)
        self.assertEqual(self.source.execute('SELECT revision_id FROM calibration_revisions').fetchall(),
                         [(revision,)])
