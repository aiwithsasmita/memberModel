"""AI-DLC code review agent for Databricks (GPT endpoint via AI Gateway)."""
from .config import ReviewConfig
from .models import Finding, ReviewResult
from .reviewer import CodeReviewer

__all__ = ["ReviewConfig", "CodeReviewer", "Finding", "ReviewResult", "review"]
__version__ = "1.0.0"


def review(diff_text: str, config_path: str = "config/review_config.yaml",
           rules_path: str = "config/rules.yaml", repo_root: str = ".", use_llm: bool = True, **kwargs):
    """One-call API for notebooks, agents and jobs: returns a ReviewResult."""
    from .llm_client import DatabricksLLMClient
    cfg = ReviewConfig(config_path, rules_path, repo_root)
    llm = DatabricksLLMClient() if use_llm else None
    return CodeReviewer(cfg, llm).review_diff(diff_text, **kwargs)
