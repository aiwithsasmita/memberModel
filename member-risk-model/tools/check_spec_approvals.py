"""CI check: any code under stages/ changed in this PR must belong to a spec folder with an approval record.

Fails when a changed spec folder has no gates/<folder>/SPEC_APPROVAL.md with Decision, Approver and Approved at filled.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="origin/main")
a = ap.parse_args()
changed = subprocess.run(["git", "diff", "--name-only", f"{a.base}...HEAD"], capture_output=True, text=True).stdout.split()
spec_folders = sorted({p.split("/")[1] for p in changed if p.startswith("specs/") and p.count("/") >= 2})
problems = []
for folder in spec_folders:
    rec = Path("gates") / folder / "SPEC_APPROVAL.md"
    if not rec.exists():
        problems.append(f"{folder}: missing {rec}")
        continue
    text = rec.read_text(encoding="utf-8")
    for field in ("Decision", "Approver", "Approved at"):
        m = re.search(rf"\*\*{field}\*\*\s*\|\s*([^|]+)\|", text)
        if not m or not m.group(1).strip() or "fills" in m.group(1):
            problems.append(f"{folder}: {field} not filled in {rec}")
if problems:
    print("Spec approval check failed:\n  " + "\n  ".join(problems))
    sys.exit(1)
print(f"Spec approvals OK for: {spec_folders or 'no spec changes'}")
