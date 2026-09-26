"""Append-only event log (aidlc_events) for the audit trail and the leadership dashboard."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone


def log_event(spark, platform_schema: str, actor: str, action: str, stage: str = "",
              change_request_id: str = "", run_id: str = "", details: dict | None = None) -> str:
    event_id = str(uuid.uuid4())
    row = [(event_id, datetime.now(timezone.utc).isoformat(), actor, action, stage, change_request_id, run_id,
            json.dumps(details or {}))]
    cols = ["event_id", "ts", "actor", "action", "stage", "change_request_id", "run_id", "details"]
    spark.createDataFrame(row, cols).write.mode("append").saveAsTable(f"{platform_schema}.aidlc_events")
    return event_id
