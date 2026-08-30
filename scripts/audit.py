#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run GitHub organize detection audit and write JSON.

Usage:
  python audit.py
  python audit.py --keep a,b --out audit.json
  python audit.py --skip-stars --repos-only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# allow `python scripts/audit.py` from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    default_desktop,
    run_audit,
    save_audit,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Audit GitHub repos + stars (detection only)")
    p.add_argument("--keep", default="", help="Comma-separated fork names to keep")
    p.add_argument("--out", default="", help="Write full audit JSON path")
    p.add_argument("--summary-only", action="store_true", help="Print summary JSON only")
    p.add_argument("--skip-fork-enrich", action="store_true")
    p.add_argument("--skip-stars", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    keep = {x.strip() for x in args.keep.split(",") if x.strip()}
    audit = run_audit(
        keep,
        skip_fork_enrich=args.skip_fork_enrich,
        skip_stars=args.skip_stars,
        progress=not args.quiet,
    )

    out = Path(args.out) if args.out else (
        default_desktop() / f"GitHub审计_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )
    save_audit(audit, out)

    summary = audit["summary"]
    print(json.dumps(summary if args.summary_only else {
        "ok": True,
        "out": str(out),
        "summary": summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
