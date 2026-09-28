"""Run the full pipeline in dependency order: ingestion, silver, load, dbt."""
import runpy
import subprocess
import sys
import time

from dotenv import load_dotenv

STEPS = [
    "ingestion.fetch_shortages",
    "ingestion.silver_shortages",
    "ingestion.fetch_recalls",
    "ingestion.silver_recalls",
    "ingestion.fetch_spl",
    "ingestion.silver_spl",
    "ingestion.fetch_decrs",
    "ingestion.silver_facilities",
    "ingestion.fetch_rxnorm",
    "ingestion.silver_rxnorm",
    "ingestion.load_silver",
    "dbt.build",
    "graph.build_graph",
]


def run_dbt():
    load_dotenv(".env")
    subprocess.run(["dbt", "build"], cwd="dbt", check=True)


def run_step(step):
    if step == "dbt.build":
        run_dbt()
    else:
        runpy.run_module(step, run_name="__main__")


def main():
    filters = sys.argv[1:]
    total_start = time.time()
    for step in STEPS:
        if filters and not any(f in step for f in filters):
            continue
        print(f"\n{'=' * 60}\n{step}\n{'=' * 60}")
        start = time.time()
        run_step(step)
        print(f"[{step} finished in {time.time() - start:.1f}s]")
    print(f"\nPipeline finished in {time.time() - total_start:.1f}s")


if __name__ == "__main__":
    main()