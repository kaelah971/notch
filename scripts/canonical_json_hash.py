#!/usr/bin/env python3
"""Canonical JSON SHA-256 helper for Notch frozen rules and evidence.

Canonical form: UTF-8 JSON with lexicographically sorted object keys and
compact separators (",", ":"). No whitespace is emitted. SHA-256 is computed
over the canonical UTF-8 bytes.

Usage:
    python scripts/canonical_json_hash.py <file.json> [--canonical]
"""

import argparse
import hashlib
import json
import sys


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hash a JSON file canonically")
    parser.add_argument("path")
    parser.add_argument("--canonical", action="store_true", help="also print canonical JSON")
    args = parser.parse_args()

    with open(args.path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    canonical = canonical_json(data)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    print(f"sha256:{digest}")
    if args.canonical:
        print(canonical)
    return 0


if __name__ == "__main__":
    sys.exit(main())
