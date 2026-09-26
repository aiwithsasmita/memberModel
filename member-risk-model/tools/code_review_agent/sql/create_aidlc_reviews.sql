-- Audit table for every code review. Run once (platform owner).
CREATE SCHEMA IF NOT EXISTS aidlc_platform;

CREATE TABLE IF NOT EXISTS aidlc_platform.aidlc_reviews (
  review_id          STRING  NOT NULL,
  reviewed_at        STRING,
  pr_id              STRING,
  change_request_id  STRING,
  git_base           STRING,
  git_head           STRING,
  verdict            STRING  COMMENT 'pass | fix | block',
  n_critical         INT,
  n_high             INT,
  n_medium           INT,
  n_low              INT,
  findings_json      STRING  COMMENT 'array of findings: rule_id, severity, file, line, title, explanation, suggested_fix, evidence, source, verified',
  files_reviewed     STRING,
  specs_used         STRING,
  model_endpoint     STRING,
  prompt_version     STRING,
  input_tokens       BIGINT,
  output_tokens      BIGINT,
  dropped_findings   INT     COMMENT 'LLM findings removed by grounding or the verify pass',
  duration_seconds   DOUBLE,
  override_reason    STRING  COMMENT 'set when a code owner overrides a block'
)
COMMENT 'AI-DLC code review agent results (one row per review)';

-- The agent identity may append; people read.
GRANT SELECT, MODIFY ON TABLE aidlc_platform.aidlc_reviews TO `sp-aidlc-agents`;
GRANT SELECT ON TABLE aidlc_platform.aidlc_reviews TO `data-science-team`;

-- Handy view for the dashboard
CREATE OR REPLACE VIEW aidlc_platform.v_review_findings AS
SELECT r.review_id, r.reviewed_at, r.pr_id, r.verdict, r.model_endpoint, r.prompt_version,
       f.rule_id, f.severity, f.file, f.line, f.source, f.verified
FROM aidlc_platform.aidlc_reviews r
LATERAL VIEW explode(from_json(r.findings_json,
  'array<struct<rule_id:string,severity:string,file:string,line:int,title:string,explanation:string,suggested_fix:string,evidence:string,source:string,verified:boolean>>')) t AS f;
