from measurement.groups import resolve_group_rows
from measurement.ledger import CalibrationLedger, FrozenCalibration
from measurement.rows import TrialRow


def freeze_revision(ledger: CalibrationLedger, revision_id: str) -> str:
    return ledger.store_freeze(revision_id)


def get_frozen_calibration(ledger: CalibrationLedger, freeze_id: str) -> FrozenCalibration:
    return ledger.get_freeze(freeze_id)


def read_frozen_group(frozen: FrozenCalibration, group_id: str) -> tuple[TrialRow, ...]:
    return resolve_group_rows(frozen.revision.groups, frozen.revision.rows, group_id)
