"""Feature creation stage entry point (01_feature_creation).

Implements: specs/001-feature-creation (spec.md, tasks.md). MRS-001 modules: M1 source profiling (Data Gate), M2 eligibility spine, M3 claims standardization, M4 diagnosis mapping.
Rules: read inputs and write outputs only through contract.yaml; all settings from config/;
MLflow only through aidlc_common.mlflow_utils.start_traced_run; never import another stage.
"""
from pathlib import Path

from aidlc_common.config import load_stage

STAGE_DIR = Path(__file__).resolve().parents[1]


def main(variables=None, spec_id="", task_id="", change_request_id=""):
    cfg = load_stage(STAGE_DIR, variables)
    # 1. validate inputs against cfg["contract"]["inputs"]
    # 2. run enabled registry entries (plugins) from cfg["sources"]
    # 3. write outputs declared in cfg["contract"]["outputs"] with aidlc_common.io.write_output
    # 4. log an event (aidlc_common.events.log_event)
    raise NotImplementedError("Implement from specs/001-feature-creation/tasks.md")


if __name__ == "__main__":
    main()
