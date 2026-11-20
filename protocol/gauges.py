from dataclasses import dataclass

from protocol.fixtures import Fixture, validate_fixture_id, validate_identifier


@dataclass(frozen=True)
class GaugeSpec:
    gauge_id: str
    fixture_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.gauge_id, 'gauge id')
        if not isinstance(self.fixture_ids, (tuple, list)) or not self.fixture_ids:
            raise ValueError('gauge must name at least one compatible fixture')
        identities = tuple(validate_fixture_id(value) for value in self.fixture_ids)
        object.__setattr__(self, 'fixture_ids', identities)

    def require_compatible(self, fixture: Fixture) -> None:
        if not isinstance(fixture, Fixture):
            raise ValueError('a fixture is required')
        if not any(fixture.matches(identity) for identity in self.fixture_ids):
            raise ValueError(f'gauge {self.gauge_id!r} is incompatible with fixture {fixture.fixture_id!r}')
