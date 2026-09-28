"""Download FDA's drug establishment registration file (DECRS) into the bronze layer."""
from datetime import datetime, timezone
from pathlib import Path

import requests

DECRS_URL = "https://www.accessdata.fda.gov/cder/drls_reg.zip"
RAW_DIR = Path("data/raw/decrs")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; rxshield/0.1)"}


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(DECRS_URL, headers=HEADERS, timeout=120)
    response.raise_for_status()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"decrs_{stamp}.zip"
    path.write_bytes(response.content)
    print(f"Saved {len(response.content) // 1024} KB to {path}")


if __name__ == "__main__":
    main()