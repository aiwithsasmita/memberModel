"""
Shared fixtures. Run the suite from the repo root with:

    python -m pytest tests

The synthetic fixtures use a small population (400 members) written to a temporary
directory, so the tests never touch data/raw/ and finish in a few seconds.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "src", REPO_ROOT / "data"):
    sys.path.insert(0, str(path))

import config  # noqa: E402

TEST_N_MEMBERS = 400


@pytest.fixture(scope="session")
def spine(tmp_path_factory):
    """A small synthetic run, joined into the member-month spine."""
    import make_synthetic_data
    import spine as spine_module

    patch = pytest.MonkeyPatch()
    patch.setattr(config, "RAW_DIR", tmp_path_factory.mktemp("raw"))
    patch.setattr(config, "N_MEMBERS", TEST_N_MEMBERS)
    try:
        mmr, claims, mor = make_synthetic_data.generate(verbose=False)
    finally:
        patch.undo()
    return spine_module.build_spine(mmr, claims, mor)


@pytest.fixture(scope="session")
def targets(spine):
    """{target_year: target_df} for every set that has a target."""
    import target as target_module

    years = [s["target_year"] for s in config.SPLITS.values() if s["target_year"] is not None]
    built, _ = target_module.build_targets_for_years(spine, years)
    return built


@pytest.fixture(scope="session")
def member_folds(spine):
    import splits as splits_module

    return splits_module.assign_member_folds(spine["member_id"].unique())


@pytest.fixture(scope="session")
def row_sets(spine, targets, member_folds):
    import splits as splits_module

    return splits_module.build_row_sets(spine, targets, member_folds)
