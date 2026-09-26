"""Gate checks: a stage task fails unless its required upstream gates are approved in aidlc_gates."""
from __future__ import annotations

from typing import Iterable, List


def missing_gates(spark, platform_schema: str, spec_id: str, required: Iterable[str]) -> List[str]:
    rows = spark.sql(
        f"SELECT gate_name FROM {platform_schema}.aidlc_gates "
        f"WHERE spec_id = '{spec_id}' AND status = 'approved'").collect()
    approved = {r["gate_name"] for r in rows}
    return [g for g in required if g not in approved]


def assert_gates(spark, platform_schema: str, spec_id: str, required: Iterable[str]) -> None:
    missing = missing_gates(spark, platform_schema, spec_id, required)
    if missing:
        raise RuntimeError(f"Blocked: gates not approved for {spec_id}: {missing}. See gates/ and aidlc_gates.")
