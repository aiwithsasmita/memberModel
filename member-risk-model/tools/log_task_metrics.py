"""Log one finished task to aidlc_task_metrics (feeds the leadership dashboard). Run in a notebook or job.

  python tools/log_task_metrics.py --task-id T014 --spec-id 002 --arm aidlc --start 2026-10-01T09:00 \
      --end 2026-10-01T12:30 --tokens 84000 --messages 22 --rework 1 --defects 0 --first-pass-tests true
"""
import argparse
from datetime import datetime

ap = argparse.ArgumentParser()
for k in ["task-id", "spec-id", "arm", "start", "end"]:
    ap.add_argument(f"--{k}", required=True)
for k in ["tokens", "messages", "rework", "defects"]:
    ap.add_argument(f"--{k}", type=int, default=0)
ap.add_argument("--first-pass-tests", default="false")
ap.add_argument("--table", default="aidlc_platform.aidlc_task_metrics")
a = ap.parse_args()

from pyspark.sql import SparkSession  # noqa: E402

row = [(a.task_id, a.spec_id, a.arm, datetime.fromisoformat(a.start), datetime.fromisoformat(a.end), a.tokens,
        a.messages, a.rework, a.defects, a.first_pass_tests.lower() == "true")]
cols = ["task_id", "spec_id", "arm", "start_ts", "end_ts", "tokens", "messages", "rework_rounds", "defects_found",
        "first_pass_tests"]
SparkSession.builder.getOrCreate().createDataFrame(row, cols).write.mode("append").saveAsTable(a.table)
print("logged", a.task_id)
