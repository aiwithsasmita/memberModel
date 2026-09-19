"""
Phase 8 -- Optum BERT member embeddings. INTERFACE ONLY.

Non-negotiable rule #8: no public model stands in for Optum BERT. There is no fallback
encoder here, no sentence-transformers, nothing downloaded. The function below defines the
contract the production implementation must satisfy and returns None until someone
implements it against the real endpoint.

config.USE_BERT_EMBEDDINGS is False by default and the whole pipeline runs with it off.
"""

import pandas as pd

import config


def get_member_embeddings(member_ids, as_of_date):
    """
    Production: frozen Optum BERT, mean-pooled over each member's token sequence
    truncated at as_of_date, reduced to ~32 dims via a PCA fit on training rows.
    Not implemented here -- no substitute model is used. Controlled by
    config.USE_BERT_EMBEDDINGS (default False).

    Contract for whoever implements it:
      returns  pd.DataFrame indexed by member_id, columns bert_00 .. bert_{N-1},
               plus .attrs["max_source_date"] = the latest source date the embeddings
               were allowed to see, so features.assert_no_future_leakage can check it.
      returns  None when the flag is off -- features.py must stay happy with that.
    """
    if not config.USE_BERT_EMBEDDINGS:
        return None

    raise NotImplementedError(
        "Optum BERT embeddings are not implemented in this rehearsal. Point this at the "
        "real frozen Optum BERT endpoint on the serverless GPU before setting "
        "config.USE_BERT_EMBEDDINGS = True. Do not substitute a public model: the whole "
        "value of this feature block is that it is that specific model on that specific "
        "member text, and a stand-in would produce numbers that look fine and mean nothing."
    )


def embedding_column_names():
    """Column names the production implementation is expected to return."""
    return [f"bert_{i:02d}" for i in range(config.BERT_EMBEDDING_DIMS)]
