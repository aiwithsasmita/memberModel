"""Structure tests for 05_model_test: config, registry and contract are valid and self-contained."""
from pathlib import Path

import yaml

STAGE = Path(__file__).resolve().parents[1]


def _y(p):
    return yaml.safe_load((STAGE / p).read_text())


def test_stage_yaml():
    s = _y("config/stage.yaml")["stage"]
    assert s["id"] == STAGE.name and s["spec"].startswith("specs/")


def test_contract_declares_outputs_with_keys():
    c = _y("contract.yaml")
    assert c["stage"] == STAGE.name
    for name, t in c["outputs"].items():
        assert t["keys"], f"output {name} has no keys"


def test_registry_entries_have_owner_and_spec():
    reg = _y("config/evaluation.yaml")
    for section in reg.values():
        if isinstance(section, dict):
            for name, e in section.items():
                if isinstance(e, dict) and "plugin" in e:
                    assert e.get("owner"), f"{name} has no owner"
                    assert e.get("spec"), f"{name} cites no spec FR"
