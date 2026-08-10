"""Class ownership metadata and historical pickle lookup compatibility."""

from __future__ import annotations

import pickle

import pytest

from src.reliability import drills, load_harness, post_start_validation, profiles
from src.reliability.load.contracts import Sample
from src.reliability.load.profiles import ReliabilityProfile
from src.reliability.operator_drills.disk_capacity import DiskCapacity
from src.reliability.post_start.contracts import PostStartCheck


@pytest.mark.parametrize(
    ("facade", "historical_module", "name", "canonical", "canonical_module"),
    [
        (
            drills,
            "src.reliability.drills",
            "DiskCapacity",
            DiskCapacity,
            "src.reliability.operator_drills.disk_capacity",
        ),
        (
            load_harness,
            "src.reliability.load_harness",
            "Sample",
            Sample,
            "src.reliability.load.contracts",
        ),
        (
            profiles,
            "src.reliability.profiles",
            "ReliabilityProfile",
            ReliabilityProfile,
            "src.reliability.load.profiles",
        ),
        (
            post_start_validation,
            "src.reliability.post_start_validation",
            "PostStartCheck",
            PostStartCheck,
            "src.reliability.post_start.contracts",
        ),
    ],
)
def test_canonical_class_metadata_and_historical_pickle_lookup_are_compatible(
    facade: object,
    historical_module: str,
    name: str,
    canonical: type[object],
    canonical_module: str,
) -> None:
    assert getattr(facade, name) is canonical
    assert canonical.__module__ == canonical_module

    historical_global = f"c{historical_module}\n{name}\n.".encode("ascii")
    assert pickle.loads(historical_global) is canonical
