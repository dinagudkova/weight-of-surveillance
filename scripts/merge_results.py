"""Merge crawl folders from several machines into one folder.

Usage: python scripts/merge_results.py data/raw/study_merged data/raw/study_mac1 data/raw/study_mac2 data/raw/study_win1 data/raw/study_win2
       (first argument = target folder, the rest = source folders)

Visits and requests are concatenated (visit ids are unique), screenshots are copied.
Running it again rebuilds the target from scratch, so new data from the sources is included.
"""
import shutil
import sys
from pathlib import Path

target, sources = Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]
if not sources:
    sys.exit(__doc__)
(target / "screens").mkdir(parents=True, exist_ok=True)
for name in ["visits.jsonl", "requests.jsonl"]:
    with open(target / name, "w", encoding="utf-8") as out:
        for src in sources:
            f = src / name
            if f.exists():
                for line in open(f, encoding="utf-8"):
                    if line.strip():
                        out.write(line if line.endswith("\n") else line + "\n")
n = 0
for src in sources:
    for shot in (src / "screens").glob("*.jpg"):
        shutil.copy2(shot, target / "screens" / shot.name)
        n += 1
visits = sum(1 for _ in open(target / "visits.jsonl", encoding="utf-8"))
print(f"Merged {len(sources)} folders into {target}: {visits} visits, {n} screenshots")
