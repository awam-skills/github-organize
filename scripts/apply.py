#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply confirmed cleanup actions from an audit JSON.

NEVER run destructive flags unless the user explicitly confirmed the list.

Examples:
  # Dry-run: show what would be deleted
  python apply.py --from audit.json --delete-forks --dry-run

  # Star upstreams then delete forks in 建议删除-无新提交 (exclude kept names)
  python apply.py --from audit.json --delete-forks --star-parents --yes \\
      --categories 建议删除-无新提交 --exclude daily_stock_analysis,limit-up-dao

  # Archive stale own repos
  python apply.py --from audit.json --archive-own --yes --categories 建议归档-长期未更新

  # Unstar archived/stale stars
  python apply.py --from audit.json --unstar --yes --categories 建议取消星标-上游已归档
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    ARCHIVE_OWN_CATEGORIES,
    DELETE_FORK_CATEGORIES,
    UNSTAR_CATEGORIES,
    archive_repo,
    auth_scopes,
    delete_repo,
    ensure_starred,
    load_audit,
    unstar_repo,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Apply GitHub organize actions from audit JSON")
    p.add_argument("--from", dest="src", required=True, help="Path to audit JSON from audit.py")
    p.add_argument("--delete-forks", action="store_true")
    p.add_argument("--star-parents", action="store_true", help="Star upstream before delete")
    p.add_argument("--archive-own", action="store_true")
    p.add_argument("--unstar", action="store_true")
    p.add_argument(
        "--categories",
        default="",
        help="Comma-separated category filter (default depends on action)",
    )
    p.add_argument("--exclude", default="", help="Comma-separated repo names to skip")
    p.add_argument("--include", default="", help="If set, only these repo names (fork/own short name or star full name)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="Actually execute (required for mutations)")
    args = p.parse_args()

    if not any([args.delete_forks, args.archive_own, args.unstar, args.star_parents]):
        p.error("Specify at least one of --delete-forks / --archive-own / --unstar / --star-parents")

    if not args.dry_run and not args.yes:
        p.error("Refusing to mutate without --yes (or pass --dry-run)")

    audit = load_audit(Path(args.src))
    repos = audit.get("repos") or []
    stars = audit.get("stars") or []
    exclude = {x.strip() for x in args.exclude.split(",") if x.strip()}
    include = {x.strip() for x in args.include.split(",") if x.strip()}
    cats = {x.strip() for x in args.categories.split(",") if x.strip()}

    results: dict = {"dry_run": args.dry_run, "actions": []}

    if args.delete_forks or args.star_parents:
        use_cats = cats or DELETE_FORK_CATEGORIES
        candidates = [
            r for r in repos
            if r.get("type") == "Fork"
            and r.get("cat") in use_cats
            and r.get("name") not in exclude
            and (not include or r.get("name") in include or r.get("full") in include)
        ]
        if args.delete_forks and not args.dry_run:
            scopes = auth_scopes()
            if scopes and "delete_repo" not in scopes:
                print(json.dumps({
                    "error": "missing_delete_repo_scope",
                    "hint": "gh auth refresh -h github.com -s delete_repo",
                    "scopes": scopes,
                }, ensure_ascii=False, indent=2))
                return 2

        for r in candidates:
            item = {"fork": r["full"], "parent": r.get("parent") or "", "cat": r["cat"]}
            if args.star_parents and r.get("parent"):
                if args.dry_run:
                    item["star"] = "would_star_or_skip"
                else:
                    item["star"] = ensure_starred(r["parent"])
            if args.delete_forks:
                if args.dry_run:
                    item["delete"] = "would_delete"
                else:
                    item["delete"] = delete_repo(r["full"])
            results["actions"].append(item)

    if args.archive_own:
        use_cats = cats or ARCHIVE_OWN_CATEGORIES
        candidates = [
            r for r in repos
            if r.get("type") == "自有"
            and r.get("cat") in use_cats
            and r.get("archived") != "是"
            and r.get("name") not in exclude
            and (not include or r.get("name") in include or r.get("full") in include)
        ]
        for r in candidates:
            item = {"repo": r["full"], "cat": r["cat"]}
            if args.dry_run:
                item["archive"] = "would_archive"
            else:
                item["archive"] = archive_repo(r["full"])
            results["actions"].append(item)

    if args.unstar:
        use_cats = cats or UNSTAR_CATEGORIES
        candidates = [
            s for s in stars
            if s.get("cat") in use_cats
            and s.get("repo") not in exclude
            and (not include or s.get("repo") in include)
        ]
        for s in candidates:
            item = {"repo": s["repo"], "cat": s["cat"]}
            if args.dry_run:
                item["unstar"] = "would_unstar"
            else:
                item["unstar"] = unstar_repo(s["repo"])
            results["actions"].append(item)

    results["count"] = len(results["actions"])
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
