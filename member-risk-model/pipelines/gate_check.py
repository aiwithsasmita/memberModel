"""Task 0 of the pipeline: fail the run if a required gate for this spec is not approved."""
import argparse

import yaml
from pyspark.sql import SparkSession

from aidlc_common.gates import missing_gates

ap = argparse.ArgumentParser()
ap.add_argument("--spec-id", default="")
ap.add_argument("--start-at", default="01_feature_creation")
ap.add_argument("--platform-schema", default="aidlc_platform")
a = ap.parse_args()

cfg = yaml.safe_load(open(__file__.replace("gate_check.py", "pipeline.yaml")))
required = cfg["gates_required"].get(a.start_at, [])
if a.spec_id and required:
    missing = missing_gates(SparkSession.builder.getOrCreate(), a.platform_schema, a.spec_id, required)
    if missing:
        raise SystemExit(f"Blocked: {missing} not approved for spec {a.spec_id}")
print(f"Gate check passed for spec={a.spec_id or 'n/a'} start_at={a.start_at}")
