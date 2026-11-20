from collections.abc import Iterable
from dataclasses import dataclass

from measurement.rows import TrialRow
from protocol.fixtures import validate_identifier


@dataclass(frozen=True)
class TrialGroup:
    group_id: str
    row_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.group_id, 'group id')
        if not isinstance(self.row_ids, (tuple, list)) or not self.row_ids:
            raise ValueError('trial group must contain at least one row')
        row_ids = tuple(validate_identifier(value, 'trial id') for value in self.row_ids)
        if len(set(row_ids)) != len(row_ids):
            raise ValueError(f'duplicate trial in group {self.group_id!r}')
        object.__setattr__(self, 'row_ids', row_ids)


def validate_groups(groups: Iterable[TrialGroup], rows: Iterable[TrialRow]) -> tuple[TrialGroup, ...]:
    available = {row.row_id for row in rows}
    accepted = {}
    for group in groups:
        if not isinstance(group, TrialGroup):
            raise ValueError('expected a trial group')
        if group.group_id in accepted:
            raise ValueError(f'duplicate group id {group.group_id!r}')
        for row_id in group.row_ids:
            if row_id not in available:
                raise KeyError(row_id)
        accepted[group.group_id] = group
    return tuple(accepted.values())


def resolve_group_rows(
    groups: tuple[TrialGroup, ...], rows: tuple[TrialRow, ...], group_id: str
) -> tuple[TrialRow, ...]:
    validate_identifier(group_id, 'group id')
    for group in groups:
        if group.group_id == group_id:
            by_id = {row.row_id: row for row in rows}
            return tuple(by_id[row_id] for row_id in group.row_ids)
    raise KeyError(group_id)
