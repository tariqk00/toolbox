#!/usr/bin/env python3
from __future__ import annotations

import argparse

from toolbox.lib.low_confidence import reprocess_low_confidence_drive_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprocess Drive low-confidence items.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum items to reprocess")
    parser.add_argument("--execute", action="store_true", help="Apply rename/move promotion for high-confidence results")
    args = parser.parse_args()

    results = reprocess_low_confidence_drive_files(limit=args.limit, execute=args.execute)
    promoted = sum(1 for item in results if item["promoted"])
    print(f"Processed {len(results)} low-confidence item(s); promoted {promoted}.")
    for item in results:
        status = "PROMOTED" if item["promoted"] else item["confidence"]
        print(f"- {item['file_id']}: {status} -> {item['target_path'] or 'Unknown'} / {item['proposed_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
