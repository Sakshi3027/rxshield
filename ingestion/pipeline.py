"""Run the full ingestion pipeline in dependency order."""
import runpy
import sys
import time

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
]


def main():
    filters = sys.argv[1:]
    total_start = time.time()
    for module in STEPS:
        if filters and not any(f in module for f in filters):
            continue
        print(f"\n{'=' * 60}\n{module}\n{'=' * 60}")
        start = time.time()
        runpy.run_module(module, run_name="__main__")
        print(f"[{module} finished in {time.time() - start:.1f}s]")
    print(f"\nPipeline finished in {time.time() - total_start:.1f}s")


if __name__ == "__main__":
    main()