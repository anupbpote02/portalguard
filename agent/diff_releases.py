"""Snapshot two portal releases and print their aria differences (no LLM involved).

Usage (portal must be running: python -m http.server 8000 --directory portal):
    python -m agent.diff_releases
    python -m agent.diff_releases --baseline http://localhost:8000/good/ --release http://localhost:8000/buggy/
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime
from urllib.error import URLError

from agent.tools import REPO_ROOT, compare_snapshots, snapshot_page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", default="http://localhost:8000/good/")
    parser.add_argument("--release", default="http://localhost:8000/buggy/")
    args = parser.parse_args()

    try:
        urllib.request.urlopen(args.baseline, timeout=3)
    except URLError:
        print(f"Portal not reachable at {args.baseline}\n"
              "Start it first:  python -m http.server 8000 --directory portal")
        return 2

    snapshot_dir = REPO_ROOT / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S") / "snapshots"
    for label, url in [("baseline", args.baseline), ("release", args.release)]:
        summary = snapshot_page(url, label, snapshot_dir=snapshot_dir)
        print(f"== snapshot_page({url!r}, {label!r}) ->")
        print(json.dumps(summary, indent=2))

    result = compare_snapshots("baseline", "release", snapshot_dir=snapshot_dir)
    print("\n== compare_snapshots('baseline', 'release') ->")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
