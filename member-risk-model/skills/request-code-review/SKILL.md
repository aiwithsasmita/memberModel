---
name: request-code-review
description: Use before opening a PR or after each fix round: run the AI-DLC code review agent and act on its findings.
---

# Running the code review agent

Locally or in a notebook:
```
aidlc-review --base origin/main --head HEAD --repo-root . \
  --config tools/code_review_agent/config/review_config.yaml --rules tools/code_review_agent/config/rules.yaml
```
- **block:** fix every critical finding before opening the PR.
- **fix:** fix high and medium findings, or explain in the PR why not.
- **UNTRACED-CHANGE:** the file isn't named by any task. Update tasks.md (spec owner approval) or drop the change.
- **UNSPECIFIED-BEHAVIOR / REQ-*:** make the code match the spec exactly, or change the spec first.
The same review runs in CI on every PR and is logged to `aidlc_platform.aidlc_reviews`.
