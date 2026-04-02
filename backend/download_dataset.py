"""
download_dataset.py
Run this once from the backend/ folder to download the 60k food database.

Usage:
  cd backend
  python download_dataset.py
"""

import urllib.request
import os
import json
import sys

URL      = "https://raw.githubusercontent.com/theoyuncu8/food_tracker_data/main/60000_food_data.json"
OUT_FILE = "food_data.json"

def main():
    if os.path.exists(OUT_FILE):
        print(f"✅  '{OUT_FILE}' already exists. Delete it to re-download.")
        # Quick check
        with open(OUT_FILE) as f:
            data = json.load(f)
        print(f"   Contains {len(data):,} food items.")
        return

    print(f"⬇️   Downloading food database from GitHub…")
    print(f"    URL: {URL}")
    print(f"    Saving to: {OUT_FILE}")

    try:
        urllib.request.urlretrieve(URL, OUT_FILE, _progress)
        print()  # newline after progress dots

        with open(OUT_FILE) as f:
            data = json.load(f)

        print(f"✅  Downloaded {len(data):,} food items successfully!")
        print(f"    File size: {os.path.getsize(OUT_FILE) / 1024 / 1024:.1f} MB")

    except Exception as e:
        print(f"\n❌  Download failed: {e}")
        print("    Make sure you have an internet connection.")
        sys.exit(1)


_last_pct = -1
def _progress(block_num, block_size, total_size):
    global _last_pct
    if total_size <= 0:
        return
    pct = int(block_num * block_size * 100 / total_size)
    pct = min(pct, 100)
    if pct != _last_pct:
        sys.stdout.write(f"\r    Progress: {pct}%  ")
        sys.stdout.flush()
        _last_pct = pct


if __name__ == "__main__":
    main()
