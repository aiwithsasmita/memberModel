-- AI-DLC platform tables (run once, platform owner). Schema: aidlc_platform
CREATE SCHEMA IF NOT EXISTS aidlc_platform;

CREATE TABLE IF NOT EXISTS aidlc_platform.aidlc_gates (
  gate_id STRING, gate_name STRING, stage STRING, spec_id STRING, change_request_id STRING,
  status STRING COMMENT 'pending | approved | rejected', approver STRING, approved_at TIMESTAMP,
  git_commit STRING, evidence_links STRING, notes STRING);

CREATE TABLE IF NOT EXISTS aidlc_platform.aidlc_events (
  event_id STRING, ts STRING, actor STRING COMMENT 'agent | person | job name', action STRING,
  stage STRING, change_request_id STRING, run_id STRING, details STRING);

CREATE TABLE IF NOT EXISTS aidlc_platform.aidlc_change_requests (
  cr_id STRING, created_at TIMESTAMP, source STRING COMMENT 'person | alert', type STRING
  COMMENT 'data_source | new_feature | feature_logic | selection | new_model | training_config | evaluation | scoring | monitor | drift_retrain',
  description STRING, status STRING, spec_folder STRING, spec_pr STRING, code_pr STRING,
  champion_version STRING, challenger_version STRING, decision STRING, decided_by STRING, decided_at TIMESTAMP);

CREATE TABLE IF NOT EXISTS aidlc_platform.aidlc_task_metrics (
  task_id STRING, spec_id STRING, arm STRING COMMENT 'aidlc | vibe', start_ts TIMESTAMP, end_ts TIMESTAMP,
  tokens BIGINT, messages INT, rework_rounds INT, defects_found INT, first_pass_tests BOOLEAN);

-- aidlc_reviews is created by tools/code_review_agent/sql/create_aidlc_reviews.sql

-- Only named approver groups may approve gates: agents and developers insert pending rows only.
GRANT SELECT ON SCHEMA aidlc_platform TO `data-science-team`;
GRANT SELECT, MODIFY ON TABLE aidlc_platform.aidlc_events TO `sp-aidlc-agents`;
GRANT SELECT, MODIFY ON TABLE aidlc_platform.aidlc_change_requests TO `sp-aidlc-agents`;
GRANT SELECT, MODIFY ON TABLE aidlc_platform.aidlc_task_metrics TO `data-science-team`;
GRANT SELECT, MODIFY ON TABLE aidlc_platform.aidlc_gates TO `sp-aidlc-ci`;   -- CI writes approvals from merged gate files
