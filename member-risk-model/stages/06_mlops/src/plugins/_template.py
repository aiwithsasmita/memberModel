"""Template for a new promotion plugin in 06_mlops.
Copy to <name>.py, register it in config/promotion.yaml, and add tests. Cite the FR IDs it implements.
"""


def run(spark, cfg: dict, entry: dict, inputs: dict):
    """cfg = stage config, entry = this registry entry, inputs = {table_name: DataFrame} from the contract.
    Return a DataFrame keyed as the contract output requires."""
    raise NotImplementedError
