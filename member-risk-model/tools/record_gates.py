"""After merge: read gate files added or changed in the merge commit and write approved rows to aidlc_gates.
Run by CI (sp-aidlc-ci is the only identity with MODIFY on aidlc_gates)."""
import argparse
import re
import subprocess
import uuid
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--commit", required=True)
ap.add_argument("--table", default="aidlc_platform.aidlc_gates")
ap.add_argument("--warehouse-id", default=None)
a = ap.parse_args()

files = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "gates/"], capture_output=True,
                       text=True).stdout.split()
rows = []
for f in files:
    if f.endswith("_template.md") or not Path(f).exists():
        continue
    t = Path(f).read_text(encoding="utf-8")
    get = lambda k: (re.search(rf"\|\s*\**{k}\**\s*\|\s*([^|]+)\|", t) or [None, ""])[1].strip()
    if get("Decision").lower().startswith("approved"):
        rows.append({"gate_id": str(uuid.uuid4()), "gate_name": Path(f).stem.replace("_", " ").title(),
                     "spec_id": Path(f).parent.name, "change_request_id": get("Change request"),
                     "stage": get("Stage"), "status": "approved", "approver": get("Approver"),
                     "approved_at": get("Approved at"), "git_commit": a.commit, "evidence_links": get("Evidence")})
print(f"{len(rows)} approved gate(s) to record")
if rows:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    wh = a.warehouse_id or next(iter(w.warehouses.list())).id
    for r in rows:
        q = lambda v: "'" + str(v).replace("'", "''") + "'"
        vals = [f"try_to_timestamp({q(v)})" if k == "approved_at" else q(v) for k, v in r.items()]
        w.statement_execution.execute_statement(
            warehouse_id=wh, statement=f"INSERT INTO {a.table} ({', '.join(r)}) VALUES ({', '.join(vals)})")
