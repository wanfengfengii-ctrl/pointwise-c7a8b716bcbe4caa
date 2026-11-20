from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from application.review import lookup_correction, sign_correction, sign_review
from application.samples import ReviewBatch, SampleInput
from archive.history import retrieve_correction, retrieve_report
from archive.storage import ArchiveStorage
from measurement.amendments import amend_trial_row, submit_trial_revision
from measurement.freezes import freeze_revision
from measurement.groups import TrialGroup
from measurement.ledger import CalibrationLedger
from measurement.rows import TrialRow
from protocol.fixtures import Fixture
from protocol.gauges import GaugeSpec
from protocol.limits import ThicknessLimits
from protocol.quantities import UnitConversion
from protocol.revisions import ProtocolStore
from release.admission import admit_station_piece
from release.inventory import AdmissionInventory
from release.issue import issue_v1_station_piece, issue_v2_station_piece


def load_example(filename):
    return json.loads(Path(__file__).with_name(filename).read_text(encoding='utf-8'))


def initialize_source(connection):
    protocols = ProtocolStore(connection)
    ledger = CalibrationLedger(connection)
    protocols.initialize()
    ledger.initialize()
    return protocols, ledger


def initialize_application(connection):
    inventory = AdmissionInventory(connection)
    storage = ArchiveStorage(connection)
    inventory.initialize()
    storage.initialize()
    return inventory, storage


def seed_calibration(protocols, ledger, *, limits=None, rows=None, groups=None):
    data = load_example('calibration.json')
    protocol_id = protocols.register(
        Fixture(data['fixture_id']), GaugeSpec(data['gauge_id'], data['gauge_fixtures']),
        UnitConversion(data['unit'], data['multiplier']),
        ThicknessLimits(*data['limits']) if limits is None else limits,
    )
    if rows is None:
        rows = tuple(TrialRow(*fields) for fields in data['rows'])
    if groups is None:
        groups = tuple(TrialGroup(*fields) for fields in data['groups'])
    revision_id = submit_trial_revision(ledger, protocols, protocol_id, rows, groups)
    return protocol_id, revision_id, freeze_revision(ledger, revision_id)


def sample_batch(acceptance_id):
    data = load_example('night-request.json')
    return ReviewBatch(acceptance_id, data['fixture_id'], tuple(SampleInput(*fields) for fields in data['samples']))


def result_summary(report):
    result, = report.results
    return {
        'sample_id': result.sample_id,
        'bias': None if result.bias is None else str(result.bias),
        'corrected_thickness': None if result.corrected_thickness is None else str(result.corrected_thickness),
        'disposition': result.disposition.value,
    }


def run_correction_demo(directory):
    """Issue a V2 piece, sign with the source closed, look up from the body only."""
    from fractions import Fraction

    from examples.correction_fixture import POINT_OVERLAP, seed_case

    source_path = Path(directory) / 'correction-source.sqlite3'
    app_path = Path(directory) / 'correction-application.sqlite3'
    with closing(sqlite3.connect(source_path)) as source:
        protocols, ledger = initialize_source(source)
        _, _, freeze_id = seed_case(protocols, ledger, POINT_OVERLAP)
        v2_raw = issue_v2_station_piece(ledger, protocols, freeze_id)
        if issue_v2_station_piece(ledger, protocols, freeze_id) != v2_raw:
            raise RuntimeError('V2 issuance is not deterministic')

    with closing(sqlite3.connect(app_path)) as offline:
        inventory, storage = initialize_application(offline)
        acceptance_id = admit_station_piece(inventory, v2_raw)
        # Re-admitting the identical bytes returns the first acceptance id.
        if admit_station_piece(inventory, v2_raw) != acceptance_id:
            raise RuntimeError('V2 re-admission changed the acceptance id')
        # The calibration source stays closed while the night shift signs.
        body, receipt = sign_correction(
            inventory, storage, acceptance_id, (0, 1), (0, 3), Fraction(1, 2),
        )
        offline_lookups = {
            str(reading): list(lookup_correction(body, reading))
            for reading in (Fraction(0), Fraction(1, 2), Fraction(1))
        }
        report_id = body['report_id']

    with closing(sqlite3.connect(app_path)) as offline:
        _, storage = initialize_application(offline)
        reloaded_body, reloaded_receipt = retrieve_correction(storage, report_id)
        if reloaded_body != body or reloaded_receipt != receipt:
            raise RuntimeError('reopened storage did not return the fixed correction table')

    expected_lookups = {
        '0': ['uncorrectable', None],
        '1/2': ['correctable', '3/2'],
        '1': ['correctable', '3/2'],
    }
    normalized = {
        reading: [state, None if correction is None else str(correction)]
        for reading, (state, correction) in offline_lookups.items()
    }
    if normalized != expected_lookups:
        raise RuntimeError('correction lookups disagree with the hand calculation')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'T10.source-closed-correction',
        'input': {'case': 'POINT_OVERLAP', 'window': ['0', '1'],
                  'limits': ['0', '3'], 'tolerance': '1/2'},
        'expected': expected_lookups,
        'actual': normalized,
        'segments': body['segments'],
        'reopen_intact': reloaded_body == body and reloaded_receipt == receipt,
        'code_paths': ['release/hull.py', 'release/issue.py', 'release/v2_codec.py',
                       'application/correction.py', 'application/review.py', 'archive/history.py'],
        'oracle': 'Reading 0 carries biases 0 and 2, no shared correction fits tolerance 1/2; '
                  'the hot-only interval (0, 1] takes the constant correction 3/2.',
    }, ensure_ascii=False, sort_keys=True))
    return 0


def main():
    expected = load_example('expected.json')
    with TemporaryDirectory(prefix='film-handoff-') as directory:
        source_path = Path(directory) / 'calibration.sqlite3'
        app_path = Path(directory) / 'application.sqlite3'
        with closing(sqlite3.connect(source_path)) as source:
            protocols, ledger = initialize_source(source)
            _, revision_id, first_freeze = seed_calibration(protocols, ledger)
            first_raw = issue_v1_station_piece(ledger, protocols, first_freeze, 'steady')
            with closing(sqlite3.connect(app_path)) as offline:
                inventory, _ = initialize_application(offline)
                first_id = admit_station_piece(inventory, first_raw)

        with closing(sqlite3.connect(app_path)) as offline:
            inventory, storage = initialize_application(offline)
            first_report, first_receipt = sign_review(inventory, storage, sample_batch(first_id))
            if result_summary(first_report) != expected['first']:
                raise RuntimeError('the first review disagrees with the hand calculation')

        with closing(sqlite3.connect(source_path)) as source:
            protocols, ledger = initialize_source(source)
            amended = amend_trial_row(
                ledger, protocols, revision_id, 'ref-two', TrialRow('ref-two', 'μm', 2, 0, 2)
            )
            second_freeze = freeze_revision(ledger, amended)
            second_raw = issue_v1_station_piece(ledger, protocols, second_freeze, 'steady')

        with closing(sqlite3.connect(app_path)) as offline:
            inventory, storage = initialize_application(offline)
            second_id = admit_station_piece(inventory, second_raw)
            second_report, second_receipt = sign_review(inventory, storage, sample_batch(second_id))

        with closing(sqlite3.connect(app_path)) as offline:
            _, storage = initialize_application(offline)
            old = retrieve_report(storage, first_report.report_id)
            new = retrieve_report(storage, second_report.report_id)
            actual = {
                'first': result_summary(first_report),
                'after_amendment': result_summary(second_report),
            }
            expected_results = {name: expected[name] for name in actual}
            downstream = {
                'old_archive_intact': (old.report, old.receipt) == (first_report, first_receipt)
                and old.provenance.freeze_id == first_freeze and old.provenance.original_bytes == first_raw,
                'new_archive_intact': (new.report, new.receipt) == (second_report, second_receipt)
                and new.provenance.freeze_id == second_freeze and new.provenance.original_bytes == second_raw,
                'different_selected_pieces': old.provenance.acceptance_id != new.provenance.acceptance_id,
            }
            downstream_expected = dict.fromkeys(downstream, True)
            if actual != expected_results or downstream != downstream_expected:
                raise RuntimeError('unexpected review or historical retrieval')
            print('POINTWISE_SCENARIO ' + json.dumps({
                'case_id': 'T9.replacement',
                'input': {
                    'station': load_example('calibration.json'),
                    'request': load_example('night-request.json'),
                    'amendment': ['ref-two', 'μm', '2', '0', '2'],
                },
                'expected': expected_results,
                'actual': actual,
                'downstream_expected': downstream_expected,
                'downstream_actual': downstream,
                'code_paths': ['measurement/amendments.py', 'release/issue.py', 'release/admission.py',
                               'application/interpolate.py', 'application/review.py', 'archive/history.py'],
                'oracle': 'At reference 1 the endpoint midpoint biases are 1/2 and 1. Subtract from 10 and compare to [19/2, 10]. Compare both reloaded bundles to the captured first signatures and issued bytes.',
            }, ensure_ascii=False, sort_keys=True))
        run_correction_demo(directory)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
