from dataclasses import dataclass


def validate_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')
    return value


def validate_fixture_id(value: object) -> str:
    return validate_identifier(value, 'fixture id')


@dataclass(frozen=True)
class Fixture:
    fixture_id: str

    def __post_init__(self) -> None:
        validate_fixture_id(self.fixture_id)

    def matches(self, other: 'Fixture | str') -> bool:
        other_id = other.fixture_id if isinstance(other, Fixture) else validate_fixture_id(other)
        return self.fixture_id == other_id
