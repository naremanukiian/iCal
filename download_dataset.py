"""
download_dataset.py — run once to download the 60k food database
Usage: python download_dataset.py
"""
import urllib.request, os, json, sys

URL      = "https://raw.githubusercontent.com/theoyuncu8/food_tracker_data/main/60000_food_data.json"
OUT_FILE = "food_data.json"

def main():
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE) as f:
            data = json.load(f)
        print(f"✅  '{OUT_FILE}' already exists — {len(data):,} food items.")
        return
    print(f"⬇️   Downloading 60k food database…")
    try:
        urllib.request.urlretrieve(URL, OUT_FILE, _prog)
        print()
        with open(OUT_FILE) as f:
            data = json.load(f)
        print(f"✅  Done! {len(data):,} items, {os.path.getsize(OUT_FILE)/1024/1024:.1f} MB")
    except Exception as e:
        print(f"\n❌  Failed: {e}")
        sys.exit(1)

_last = -1
def _prog(b, bs, total):
    global _last
    if total <= 0: return
    pct = min(int(b*bs*100/total), 100)
    if pct != _last:
        sys.stdout.write(f"\r    {pct}%  "); sys.stdout.flush(); _last = pct

if __name__ == "__main__":
    main()
