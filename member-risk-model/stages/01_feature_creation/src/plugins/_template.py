"""Template for a new sources plugin in 01_feature_creation.
Copy to <name>.py, register it in config/sources.yaml, and add tests. Cite the FR IDs it implements.
"""


def run(spark, cfg: dict, entry: dict, inputs: dict):
    """cfg = stage config, entry = this registry entry, inputs = {table_name: DataFrame} from the contract.
    Return a DataFrame keyed as the contract output requires."""
    raise NotImplementedError
