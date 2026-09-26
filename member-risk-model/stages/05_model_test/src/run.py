"""Model test stage entry point (05_model_test).

Implements: specs/005-model-test (spec.md, tasks.md). MRS-001 modules: M14 evaluation vs CMS (Model Gate), champion vs challenger comparison.
Rules: read inputs and write outputs only through contract.yaml; all settings from config/;
MLflow only through aidlc_common.mlflow_utils.start_traced_run; never import another stage.
"""
from pathlib import Path

from aidlc_common.config import load_stage

STAGE_DIR = Path(__file__).resolve().parents[1]


def main(variables=None, spec_id="", task_id="", change_request_id=""):
    cfg = load_stage(STAGE_DIR, variables)
    # 1. validate inputs against cfg["contract"]["inputs"]
    # 2. run enabled registry entries (plugins) from cfg["evaluation"]
    # 3. write outputs declared in cfg["contract"]["outputs"] with aidlc_common.io.write_output
    # 4. log an event (aidlc_common.events.log_event)
    raise NotImplementedError("Implement from specs/005-model-test/tasks.md")


if __name__ == "__main__":
    main()
