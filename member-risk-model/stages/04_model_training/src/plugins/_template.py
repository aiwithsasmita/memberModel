"""Template for a new models plugin in 04_model_training.
Copy to <name>.py, register it in config/models.yaml, and add tests. Cite the FR IDs it implements.
"""


def run(spark, cfg: dict, entry: dict, inputs: dict):
    """cfg = stage config, entry = this registry entry, inputs = {table_name: DataFrame} from the contract.
    Return a DataFrame keyed as the contract output requires."""
    raise NotImplementedError
