import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rerun_from_changes import plan, task_key  # noqa: E402

CFG = yaml.safe_load((Path(__file__).resolve().parents[2] / "pipelines" / "pipeline.yaml").read_text())


def test_feature_change_reruns_from_stage_02():
    p = plan(["stages/02_feature_engineering/config/features.yaml", "README.md"], CFG)
    assert p["start_at"] == "02_feature_engineering" and p["tasks"][-1] == "06_mlops"


def test_model_change_skips_upstream():
    p = plan(["stages/04_model_training/src/plugins/catboost.py"], CFG)
    assert p["tasks"] == ["04_model_training", "05_model_test", "06_mlops"]


def test_common_change_rebuilds_all():
    assert plan(["common/src/aidlc_common/io.py"], CFG)["start_at"] == "01_feature_creation"


def test_docs_only_change_runs_nothing():
    assert plan(["docs/x.md", "specs/002-feature-engineering/spec.md"], CFG)["start_at"] is None


def test_task_key():
    assert task_key("04_model_training") == "s04_model_training"
