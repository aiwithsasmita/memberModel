# Databricks notebook source
# MAGIC %md
# MAGIC # AI-DLC code review (in-workspace run)
# MAGIC Reviews `head` against `base` in this Git folder, writes the result to `aidlc_platform.aidlc_reviews`,
# MAGIC and traces every LLM call in MLflow. Used by the change agent and for ad-hoc reviews.

# COMMAND ----------
dbutils.widgets.text("base", "origin/main")
dbutils.widgets.text("head", "HEAD")
dbutils.widgets.text("change_request_id", "")
base = dbutils.widgets.get("base")
head = dbutils.widgets.get("head")
cr = dbutils.widgets.get("change_request_id") or None

# COMMAND ----------
import mlflow
from aidlc_review.cli import main

mlflow.set_experiment("/Shared/aidlc/code_review")
with mlflow.start_run(run_name=f"review {head}"):
    mlflow.set_tags({"change_request_id": cr or "", "base": base, "head": head})
    args = ["--base", base, "--head", head, "--repo-root", ".", "--write-delta", "spark",
            "--json", "/tmp/review.json"]
    if cr:
        args += ["--change-request", cr]
    exit_code = main(args)
    mlflow.log_artifact("/tmp/review.json")

# COMMAND ----------
import json
result = json.load(open("/tmp/review.json"))
dbutils.jobs.taskValues.set("verdict", result["verdict"])
dbutils.notebook.exit(json.dumps({"verdict": result["verdict"], "review_id": result["review_id"]}))
