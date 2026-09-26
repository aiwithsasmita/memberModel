import os
from pathlib import Path

import pytest

from aidlc_common.config import enabled, load_config
from aidlc_common.contracts import load_contract
from aidlc_common.mlflow_utils import build_tags

ROOT = Path(__file__).resolve().parents[2]


def test_every_stage_config_and_contract_loads():
    vars_ = {"catalog": "mrs_dev", "source_catalog": "src_dev", "platform_schema": "aidlc_platform",
             "claude_endpoint": "c", "gpt_endpoint": "g"}
    stages = sorted((ROOT / "stages").iterdir())
    assert len(stages) == 8
    for s in stages:
        cfg = load_config(s / "config" / "stage.yaml", vars_)
        assert cfg["stage"]["id"] == s.name
        c = load_contract(s / "contract.yaml", vars_)
        assert c.outputs, f"{s.name} declares no outputs"


def test_missing_variable_fails_loudly(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("table: ${nope}.t")
    os.environ.pop("nope", None)
    with pytest.raises(KeyError):
        load_config(p)


def test_enabled_filter():
    reg = {"models": {"a": {"enabled": True}, "b": {"enabled": False}, "c": {}}}
    assert set(enabled(reg, "models")) == {"a", "c"}


def test_tags_required(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "abc")
    assert build_tags("002", "T010", "CR-1", "02")["git_commit"] == "abc"
    with pytest.raises(ValueError):
        build_tags("", "T010", "CR-1", "02")


def test_stages_never_import_each_other():
    for py in (ROOT / "stages").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        own = py.relative_to(ROOT / "stages").parts[0]
        for other in (p.name for p in (ROOT / "stages").iterdir() if p.name != own):
            assert other not in text.replace("stages/" + own, ""), f"{py} references {other}"
