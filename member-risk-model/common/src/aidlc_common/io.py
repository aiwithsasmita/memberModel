"""Read and write stage tables with Delta versions, so every run records exactly which data it used."""
from __future__ import annotations


def delta_version(spark, table: str) -> int:
    return int(spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()[0]["version"])


def read_input(spark, table: str, version: int | None = None):
    """Read a contract input, optionally pinned to a Delta version. Returns (df, version)."""
    v = delta_version(spark, table) if version is None else version
    df = spark.read.option("versionAsOf", v).table(table)
    return df, v


def write_output(df, table: str, mode: str = "overwrite", partition_by=None) -> int:
    """Write a contract output and return the new Delta version."""
    w = df.write.format("delta").mode(mode)
    if partition_by:
        w = w.partitionBy(*partition_by)
    w.saveAsTable(table)
    return delta_version(df.sparkSession, table)
