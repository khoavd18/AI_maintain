"""Compatibility facade for the Phase 2 v2 dataset builder."""

from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.phase2_v2.assembly import build_dataset
from evaluation.phase2_v2.dataset_spec import DEFAULT_OUTPUT


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    build_dataset(_parse_args().output)
