from collections.abc import Iterable

from measurement.groups import TrialGroup, validate_groups
from measurement.ledger import CalibrationLedger
from measurement.rows import TrialRow, normalize_trial_batch, normalize_trial_row
from protocol.fixtures import validate_identifier
from protocol.revisions import ProtocolStore


def submit_trial_revision(
    ledger: CalibrationLedger,
    protocols: ProtocolStore,
    protocol_id: str,
    rows: Iterable[TrialRow] = (),
    groups: Iterable[TrialGroup] = (),
    *,
    parent_id: str | None = None,
) -> str:
    protocol = protocols.get(protocol_id)
    previous_rows = ()
    previous_groups = ()
    if parent_id is not None:
        parent = ledger.get_revision(parent_id)
        if parent.protocol_id != protocol_id:
            raise ValueError('parent revision belongs to a different protocol')
        previous_rows = parent.rows
        previous_groups = parent.groups

    try:
        new_rows = tuple(rows)
        new_groups = tuple(groups)
    except TypeError as error:
        raise ValueError('rows and groups must be iterable') from error

    normalized = normalize_trial_batch(new_rows, protocol.conversion)
    previous_ids = {row.row_id for row in previous_rows}
    for row in normalized:
        if row.row_id in previous_ids:
            raise ValueError(f'original trial {row.row_id!r} requires an amendment')

    all_rows = previous_rows + new_rows
    checked_groups = validate_groups(new_groups, all_rows)
    all_groups = {group.group_id: group for group in previous_groups}
    all_groups.update((group.group_id, group) for group in checked_groups)
    return ledger.store_revision(protocol_id, parent_id, all_rows, tuple(all_groups.values()))


def amend_trial_row(
    ledger: CalibrationLedger,
    protocols: ProtocolStore,
    parent_id: str,
    row_id: str,
    replacement: TrialRow,
) -> str:
    validate_identifier(row_id, 'trial id')
    parent = ledger.get_revision(parent_id)
    protocol = protocols.get(parent.protocol_id)
    if not any(row.row_id == row_id for row in parent.rows):
        raise KeyError(row_id)
    if not isinstance(replacement, TrialRow) or replacement.row_id != row_id:
        raise ValueError('replacement must preserve the original trial id')
    normalize_trial_row(replacement, protocol.conversion)
    rows = tuple(replacement if row.row_id == row_id else row for row in parent.rows)
    return ledger.store_revision(parent.protocol_id, parent_id, rows, parent.groups)
