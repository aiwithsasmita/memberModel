# AI-DLC Code Review Agent (Databricks + GPT endpoint)

Reviews every pull request against **your Spec Kit spec, tasks and constitution**, using a GPT model served
through Databricks AI Gateway. Every changed file must trace to a task, every requirement a completed task
references must be implemented exactly, and anything the spec doesn't ask for is flagged as an assumption.
Posts the verdict on the PR, logs every review to a Delta table and traces every model call in MLflow.

## How it works

```
PR diff
  │
  ├─ 1. Static checks        regex rules on added lines (PHI in logs, secrets, prod writes, random splits,
  │                           hardcoded years, driver collects, untagged MLflow runs). Free, instant, never hallucinate.
  ├─ 2. Structural checks    src changed but no tests; locked evaluation code changed without a spec change
  ├─ 3. Spec Kit trace       reads specs/*/spec.md + tasks.md + plan.md:
  │                           · every changed file must be named by a task (else UNTRACED-CHANGE)
  │                           · spec with NEEDS CLARIFICATION → OPEN-CLARIFICATION (blocks)
  │                           · tasks marked [X] whose files don't exist → TASK-FILE-MISSING
  ├─ 4. Exact spec context   ALL FR-### and SC-###, acceptance scenarios of the touched user stories, the touched
  │                           task lines, plan excerpt. No keyword guessing.
  ├─ 5. Three review lenses  spec conformance (incl. UNSPECIFIED-BEHAVIOR = assumptions) · constitution · correctness
  ├─ 6. Requirement check    each FR referenced by a completed task touching these files: implemented / partial /
  │                           missing / contradicted
  ├─ 7. Grounding filter     drops findings that don't quote real added code; fixes wrong line numbers
  ├─ 8. Verify + confidence  second pass scores 0–100; only ≥ 80 kept (same threshold as Anthropic's code-review plugin)
  └─ 9. Verdict              block (verified critical) · fix (high/medium) · pass
        → PR review with inline comments · Delta row in aidlc_platform.aidlc_reviews · MLflow trace
```

Why this design is strong:
- **Deterministic + AI together.** Known patterns are caught by code with zero false negatives; the model handles
  meaning (leakage logic, spec conformance, correctness).
- **Spec-exact.** Scope comes from your tasks.md (which task names which file), and the reviewer gets every
  requirement of the feature verbatim. Code not asked for by a task or requirement is flagged, not accepted.
- **Low noise.** Grounding + verify remove made-up or speculative findings, so developers trust it.
- **Measured.** `eval/` scores recall and false alarms; rerun on every prompt, rule or model change.
- **Governed.** Config and rules change only through PRs; every review is auditable.

## How it fits with Spec Kit and the marketplace

| Tool | When | Checks | Code? |
| --- | --- | --- | --- |
| `/speckit.analyze` (you have it) | Before implementing | spec ↔ plan ↔ tasks consistency, gaps, constitution | No |
| **This agent** | Every pull request, in CI, on Databricks | code ↔ tasks ↔ requirements ↔ constitution, plus bugs, leakage, PHI | Yes, per PR |
| `spec-kit-verify` (community extension) | Optional, when a whole feature is done | task completion, requirement and scenario coverage | Yes, whole feature |
| Anthropic `code-review` plugin | Optional, in Claude Code | CLAUDE.md compliance, bugs, git history; confidence ≥ 80 | Yes, general |

Keep `/speckit.analyze` as the gate **before** `/speckit.implement` (no CRITICAL issues allowed), and this agent as
the required check **on every PR**. The Anthropic plugin and CodeRabbit are general reviewers and aren't tied to
Spec Kit requirements or your Databricks endpoint, so they don't replace this agent.

## Make your tasks.md traceable (important)

The agent links code to requirements through `tasks.md`. Two conventions make it exact:

1. **Every task names its files** (Spec Kit already asks for exact file paths).
2. **Every task lists the requirements it implements**, in brackets after the story label:

```
- [X] T014 [US1] (FR-003, FR-004) Build ER utilization features in src/features/utilization.py
```

Without FR IDs on tasks the agent still checks spec conformance, but it can't do the requirement-by-requirement
check (step 6). Add this convention to your tasks template (a Spec Kit preset) so every new tasks.md follows it.

## Files

| Path | What it is |
| --- | --- |
| `config/review_config.yaml` | Endpoint, limits, spec map, protected paths, verdict rules, outputs |
| `config/rules.yaml` | Static, structural and LLM rules (add your own here) |
| `src/aidlc_review/` | The agent: diff parser, checks, Spec Kit tracing (`spec_trace.py`), context, prompts, LLM client, reviewer, sinks, CLI |
| `eval/cases/` + `eval/run_eval.py` | Known-bad and known-clean diffs, scored and logged to MLflow |
| `tests/` | Unit tests (fake LLM, no network) |
| `sql/create_aidlc_reviews.sql` | Audit table, grants, and a findings view for the dashboard |
| `.github/workflows/ai-code-review.yml` | Runs on every PR |
| `resources/code_review_jobs.yml` | Bundle jobs: in-workspace review and weekly evaluation |
| `notebooks/run_review.py` | Notebook entry used by the job and by other agents |

## Setup (one time)

1. **Endpoint:** create an AI Gateway / serving endpoint for your GPT model and put its name in
   `config/review_config.yaml` → `llm.endpoint`. Turn on usage tracking and inference tables.
2. **Identity:** give `sp-aidlc-agents` `CAN QUERY` on the endpoint and `MODIFY` on the audit table.
3. **Table:** run `sql/create_aidlc_reviews.sql`.
4. **Spec Kit paths:** check `spec_trace.features_root` (default `specs`) and `constitution_paths`
   (default `.specify/memory/constitution.md` and `AGENTS.md`). `spec_map` is only a fallback for files no task names.
5. **Install in the repo:** copy this folder to `tools/code_review_agent/` in your model repo.
6. **CI:** add the workflow and repo secrets (`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`,
   `DATABRICKS_CLIENT_SECRET`; optionally `DATABRICKS_TOKEN` + `DATABRICKS_WAREHOUSE_HTTP_PATH` for the audit table).
7. **Branch protection:** make the `ai-code-review` check required on `main`. A `block` verdict fails the check;
   a code owner can override by commenting `/override-review <reason>` (record the reason in `override_reason`).
8. **Bundle:** include `resources/code_review_jobs.yml` from `databricks.yml` and deploy.

## Use

```bash
pip install -e ".[ci,dev]"
pytest -q                                              # unit tests
aidlc-review --base origin/main --head HEAD --no-llm   # static + structural only
aidlc-review --base origin/main --head HEAD            # full review (needs Databricks auth)
python eval/run_eval.py --mlflow-experiment /Shared/aidlc/code_review_eval
```

From Python (other agents, notebooks):

```python
from aidlc_review import review
result = review(diff_text, repo_root=".", change_request_id="CR-014")
result.verdict, result.findings
```

## Prove it works before relying on it

Static checks alone score **83% rule recall** on the included cases: they miss the leakage case, which needs the
model. Run `eval/run_eval.py` with the endpoint and target:

| Metric | Target |
| --- | --- |
| Rule recall on bad cases | ≥ 90% |
| Correct block / no-block decision | ≥ 90% |
| High/critical false alarms on clean cases | ≤ 10% |

Grow `eval/cases/` to 25+ cases from real bugs you've seen (one folder per case: `diff.patch` + `expected.yaml`).
Log each eval run to MLflow and compare prompt versions before changing `prompt_version`.

## Tuning

- Cost → each chunk makes 3 lens calls + 1 conformance call + 1 verify call. Drop a lens in `llm.lenses` if needed.
- Too noisy → raise `verify.min_confidence` or `output.min_inline_severity`, tighten rule descriptions, or set `llm.verifier_endpoint` to a
  stronger model.
- Missing issues → add a static rule if the pattern is regular; otherwise sharpen the LLM rule text and add a case.
- Large PRs → lower `limits.max_chars_per_chunk` (more, smaller calls) or ask for smaller PRs.
- Structured output unsupported on your endpoint → the client falls back to JSON mode, then to plain text parsing.
