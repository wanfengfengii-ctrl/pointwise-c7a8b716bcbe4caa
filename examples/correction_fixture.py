"""Calibration inputs shared by the correction examples and the V1 preview."""
from contextlib import closing
import json
import sqlite3

from application.review import sign_review
from application.samples import ReviewBatch, SampleInput
from examples.demo import initialize_application, initialize_source, seed_calibration
from measurement.groups import TrialGroup
from measurement.rows import TrialRow
from release.admission import admit_station_piece
from release.issue import issue_v1_station_piece


POINT_OVERLAP = (
    ("cold", (("cold-zero", 0, 0),)),
    ("hot", (("hot-zero", 0, 2), ("hot-one", 1, 2))),
)
TRIANGLE_AND_GAP = (
    ("triangle", (("triangle-a", 0, 0), ("triangle-b", 0, 2), ("triangle-c", 2, 2))),
    ("isolated", (("isolated-point", 4, 2),)),
)


def seed_case(protocols, ledger, groups):
    rows = tuple(
        TrialRow(row_id, "μm", reading, 0, bias)
        for _, trials in groups
        for row_id, reading, bias in trials
    )
    group_records = tuple(
        TrialGroup(name, tuple(row_id for row_id, _, _ in trials))
        for name, trials in groups
    )
    return seed_calibration(protocols, ledger, rows=rows, groups=group_records)


def main():
    with closing(sqlite3.connect(":memory:")) as offline:
        inventory, storage = initialize_application(offline)
        with closing(sqlite3.connect(":memory:")) as source:
            protocols, ledger = initialize_source(source)
            _, _, freeze_id = seed_case(protocols, ledger, POINT_OVERLAP)
            accepted = {}
            for group_id, _ in POINT_OVERLAP:
                raw = issue_v1_station_piece(ledger, protocols, freeze_id, group_id)
                accepted[group_id] = admit_station_piece(inventory, raw)
            _, _, triangle_freeze = seed_case(protocols, ledger, TRIANGLE_AND_GAP)
            try:
                issue_v1_station_piece(ledger, protocols, triangle_freeze, "triangle")
            except ValueError:
                pass
            else:
                raise RuntimeError("V1 issued a single-valued curve for the triangle group")

        actual = {}
        for group_id, acceptance_id in accepted.items():
            batch = ReviewBatch(acceptance_id, "film-bench-a", (SampleInput("strip", 0, 10),))
            report, _ = sign_review(inventory, storage, batch)
            result, = report.results
            actual[group_id] = [str(result.bias), str(result.corrected_thickness)]
        expected = {"cold": ["0", "10"], "hot": ["2", "8"]}
        if actual != expected:
            raise RuntimeError(f"unexpected V1 freeze results {actual!r}")
        print(json.dumps({"reading": "0", "v1_bias_and_thickness": actual,
                          "v1_triangle": "rejected"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
