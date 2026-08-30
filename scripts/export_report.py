#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export GitHub repo + stars cleanup report to Excel.

Requires: gh (authenticated), Python 3.9+, openpyxl
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

NOW = datetime.now(timezone.utc)

TOPIC_LIST_MAP = [
    (("llm", "openai", "chatgpt", "ai", "langchain", "gpt", "agent", "rag"), "AI/LLM"),
    (("stock", "quant", "trading", "finance", "quantitative"), "量化/股票"),
    (("vue", "vuejs", "react", "frontend", "css", "webpack", "vite"), "前端"),
    (("nodejs", "node", "nestjs", "express", "egg"), "Node/后端"),
    (("docker", "devops", "kubernetes", "k8s", "cli", "shell"), "工具/DevOps"),
    (("android", "autojs", "hamibot"), "Android/自动化"),
    (("machine-learning", "deep-learning", "pytorch", "tensorflow"), "机器学习"),
]

REPO_PRIO = {
    "建议删除-无新提交": 0,
    "建议评估后删除": 1,
    "建议评估-有提交但很久未用": 2,
    "建议归档-长期未更新": 3,
    "半活跃": 4,
    "建议人工确认": 5,
    "保留-有本人提交": 6,
    "保留-近期在用": 7,
    "保留-你指定保留": 8,
    "活跃维护": 9,
    "已归档": 10,
}

STAR_PRIO = {
    "建议取消星标-上游已归档": 0,
    "建议评估取消-长期未更新": 1,
    "可保留但标为过时": 2,
    "保留-一般参考": 3,
    "保留-上游仍活跃": 4,
    "近期星标-保留并归类": 5,
}


def run_gh(args: list[str]) -> str:
    r = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh failed: {r.stderr or r.stdout}")
    return r.stdout


def days_ago(iso: str | None) -> int | None:
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (NOW - dt).days


def get_login() -> str:
    return json.loads(run_gh(["api", "user", "--jq", "{login:.login}"]))["login"]


def fetch_repos(login: str) -> list[dict]:
    return json.loads(
        run_gh(
            [
                "repo",
                "list",
                login,
                "--limit",
                "500",
                "--json",
                "name,nameWithOwner,isFork,isPrivate,isArchived,primaryLanguage,"
                "pushedAt,updatedAt,createdAt,stargazerCount,description,url",
            ]
        )
    )


def enrich_fork(login: str, repo: dict) -> None:
    name = repo["name"]
    full = f"{login}/{name}"
    try:
        detail = json.loads(
            run_gh(
                [
                    "api",
                    f"repos/{full}",
                    "--jq",
                    "{parent:.parent.full_name,parent_default:.parent.default_branch,"
                    "default:.default_branch}",
                ]
            )
        )
    except Exception:
        repo["_parent"] = None
        repo["_ahead"] = None
        repo["_behind"] = None
        repo["_user_commits"] = None
        return

    parent = detail.get("parent")
    repo["_parent"] = parent
    fork_branch = detail.get("default") or "main"
    parent_branch = detail.get("parent_default") or "main"

    # Prefer same branch name on parent
    if parent:
        parent_owner = parent.split("/")[0]
        try:
            run_gh(["api", f"repos/{parent}/branches/{fork_branch}"])
            parent_branch = fork_branch
        except Exception:
            pass

        base = f"{parent_owner}:{parent_branch}"
        head = f"{login}:{fork_branch}"
        encoded = f"{base.replace(':', '%3A')}...{head.replace(':', '%3A')}"
        try:
            cmp_ = json.loads(
                run_gh(
                    [
                        "api",
                        f"repos/{full}/compare/{encoded}",
                        "--jq",
                        "{ahead_by,behind_by,status}",
                    ]
                )
            )
            repo["_ahead"] = cmp_.get("ahead_by")
            repo["_behind"] = cmp_.get("behind_by")
        except Exception:
            repo["_ahead"] = None
            repo["_behind"] = None
    else:
        repo["_ahead"] = None
        repo["_behind"] = None

    try:
        out = run_gh(["api", f"repos/{full}/commits?author={login}&per_page=1"])
        body = out.strip()
        if body in ("", "[]"):
            repo["_user_commits"] = 0
        else:
            arr = json.loads(body)
            repo["_user_commits"] = 1 if arr else 0
    except Exception as e:
        err = str(e).lower()
        if "empty" in err or "409" in err:
            repo["_user_commits"] = 0
        else:
            repo["_user_commits"] = None


def classify_repo(r: dict, keep: set[str]) -> tuple[str, str]:
    name = r["name"]
    d = days_ago(r.get("pushedAt"))
    is_fork = r.get("isFork")
    archived = r.get("isArchived")
    desc = (r.get("description") or "").strip()
    stars = r.get("stargazerCount") or 0
    user_c = r.get("_user_commits")
    ahead = r.get("_ahead")

    if is_fork:
        if name in keep:
            return "保留-你指定保留", "继续保留；若只作参考可读，可考虑取消 fork 关系改收藏上游。"
        if d is not None and d <= 180 and user_c == 1:
            return "保留-近期在用", "有近期活动或本人提交，建议保留；重要改动可考虑独立成仓或向上游提 PR。"
        if user_c == 0 and (ahead == 0 or ahead is None):
            return "建议删除-无新提交", "相对上游无领先提交且默认分支无本人 commit；删除前给上游打星（若未星标）。"
        if user_c == 0 and ahead and ahead > 0:
            return "建议评估后删除", "无本人提交但 ahead>0（可能是分支漂移）；确认无独特改动后删除并星标上游。"
        if user_c == 1:
            if d is not None and d > 730:
                return (
                    "建议评估-有提交但很久未用",
                    "曾有本人提交但超过约 2 年未推送；确认补丁无价值则删 fork，有价值则开 PR 或迁独立仓。",
                )
            return "保留-有本人提交", "保留；评估是否向上游贡献，或整理成独立项目。"
        return "建议人工确认", "信息不完整，打开仓库确认是否还有本地改动需求。"

    if archived:
        return "已归档", "保持归档即可；若不需要公开历史可改为私有或删除。"
    if d is not None and d <= 180:
        tips = []
        if not desc:
            tips.append("建议补充 description 与 topics")
        return ("活跃维护", "；".join(tips) if tips else "继续维护；适合 pin 到主页。")
    if d is not None and d <= 365:
        return "半活跃", "半年~1 年未更新；决定是否继续维护，否则准备归档。"
    if d is not None and d > 365:
        tip = "超过 1 年未推送，建议 Archive。"
        if not desc:
            tip += " 无描述，归档前可补一句说明用途。"
        if stars > 0:
            tip += f" 已有 {stars} star，归档优于删除。"
        return "建议归档-长期未更新", tip
    return "建议人工确认", "缺少推送时间等信息。"


def fetch_stars(tmp: Path) -> list[dict]:
    query = """query($cursor: String) {
  viewer {
    starredRepositories(first: 50, after: $cursor, orderBy: {field: STARRED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        starredAt
        node {
          nameWithOwner
          url
          description
          isArchived
          isFork
          stargazerCount
          pushedAt
          primaryLanguage { name }
          repositoryTopics(first: 12) { nodes { topic { name } } }
          owner { login }
        }
      }
    }
  }
}"""
    qpath = tmp / "github-organize-stars.graphql"
    qpath.write_text(query, encoding="utf-8")
    stars: list[dict] = []
    cursor = None
    while True:
        args = ["api", "graphql", "-F", f"query=@{qpath}"]
        if cursor:
            args += ["-f", f"cursor={cursor}"]
        data = json.loads(run_gh(args))
        if data.get("errors"):
            raise RuntimeError(str(data["errors"]))
        sr = data["data"]["viewer"]["starredRepositories"]
        for e in sr["edges"]:
            n = e["node"]
            stars.append(
                {
                    "starredAt": e["starredAt"],
                    "nameWithOwner": n["nameWithOwner"],
                    "url": n["url"],
                    "description": n.get("description"),
                    "isArchived": n.get("isArchived"),
                    "isFork": n.get("isFork"),
                    "stargazerCount": n.get("stargazerCount"),
                    "pushedAt": n.get("pushedAt"),
                    "language": (n.get("primaryLanguage") or {}).get("name"),
                    "topics": [
                        x["topic"]["name"]
                        for x in (n.get("repositoryTopics") or {}).get("nodes") or []
                    ],
                    "owner": (n.get("owner") or {}).get("login"),
                }
            )
        print(f"  starred: {len(stars)}/{sr['totalCount']}", flush=True)
        if not sr["pageInfo"]["hasNextPage"]:
            break
        cursor = sr["pageInfo"]["endCursor"]
    return stars


def suggest_list(topics, language, desc) -> str:
    tset = set(topics or [])
    blob = (" ".join(topics or []) + " " + (desc or "") + " " + (language or "")).lower()
    for keys, label in TOPIC_LIST_MAP:
        if any(k in tset or k in blob for k in keys):
            return label
    if language in ("JavaScript", "TypeScript", "Vue"):
        return "前端"
    if language == "Python":
        return "AI/LLM或量化-待细分"
    if language in ("Go", "Rust", "Java", "C++"):
        return "后端/系统"
    return "待读/未分类"


def classify_star(s: dict) -> tuple[str, str, str]:
    d = days_ago(s.get("pushedAt"))
    starred_days = days_ago(s.get("starredAt"))
    lst = suggest_list(s.get("topics"), s.get("language"), s.get("description"))
    if s.get("isArchived"):
        return "建议取消星标-上游已归档", f"上游已 archived；若不再参考可取消星标。建议列表：{lst}", lst
    if d is not None and d > 365 * 3:
        return "建议评估取消-长期未更新", f"上游超过约 3 年未推送（{d} 天）；过时技术栈可 unstar。建议列表：{lst}", lst
    if d is not None and d > 365 * 2:
        return "可保留但标为过时", f"约 2–3 年未更新；若仍有参考价值保留并放入「已过时」列表。建议列表：{lst}", lst
    if starred_days is not None and starred_days <= 90:
        return "近期星标-保留并归类", f"近 90 天内星标；优先归入 Lists。建议列表：{lst}", lst
    if d is not None and d <= 365:
        return "保留-上游仍活跃", f"上游一年内有更新；保留并归入 Lists。建议列表：{lst}", lst
    return "保留-一般参考", f"可保留；整理时归入 Lists。建议列表：{lst}", lst


def row_fill(cat: str):
    fills = {
        "建议删除": PatternFill("solid", fgColor="FCE4EC"),
        "建议归档": PatternFill("solid", fgColor="FFF3E0"),
        "建议评估": PatternFill("solid", fgColor="FFF8E1"),
        "建议取消": PatternFill("solid", fgColor="FCE4EC"),
        "活跃": PatternFill("solid", fgColor="E8F5E9"),
        "保留": PatternFill("solid", fgColor="E3F2FD"),
        "已归档": PatternFill("solid", fgColor="ECEFF1"),
        "近期": PatternFill("solid", fgColor="E8F5E9"),
    }
    for k, v in fills.items():
        if k in (cat or ""):
            return v
    return None


def style_header(ws, cols):
    fill = PatternFill("solid", fgColor="1F4E79")
    font = Font(color="FFFFFF", bold=True)
    for i, c in enumerate(cols, 1):
        cell = ws.cell(1, i, c)
        cell.fill = fill
        cell.font = font


def autosize(ws, max_width=48):
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        length = 0
        for cell in col[:200]:
            val = "" if cell.value is None else str(cell.value)
            length = max(length, min(len(val), max_width))
        ws.column_dimensions[letter].width = max(12, min(max_width, length + 2))


def write_excel(out: Path, login: str, repo_rows: list[dict], star_rows: list[dict], keep: set[str]) -> None:
    wb = Workbook()
    wrap = Alignment(wrap_text=True, vertical="top")
    thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    ws0 = wb.active
    ws0.title = "汇总说明"
    ws0["A1"] = f"GitHub 整理建议（{login}）"
    ws0["A1"].font = Font(bold=True, size=14)
    ws0["A2"] = f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    own_n = sum(1 for r in repo_rows if r["type"] == "自有")
    fork_n = sum(1 for r in repo_rows if r["type"] == "Fork")
    ws0["A3"] = f"仓库总数: {len(repo_rows)}（自有 {own_n} / Fork {fork_n}）"
    ws0["A4"] = f"星标总数: {len(star_rows)}"
    if keep:
        ws0["A5"] = "指定保留 Fork: " + ", ".join(sorted(keep))

    ws0["A7"] = "仓库处理分类统计"
    ws0["A7"].font = Font(bold=True)
    ws0["A8"] = "分类"
    ws0["B8"] = "数量"
    rc = Counter(r["cat"] for r in repo_rows)
    row_i = 9
    for k, v in sorted(rc.items(), key=lambda x: -x[1]):
        ws0[f"A{row_i}"] = k
        ws0[f"B{row_i}"] = v
        row_i += 1

    row_i += 1
    ws0[f"A{row_i}"] = "星标处理分类统计"
    ws0[f"A{row_i}"].font = Font(bold=True)
    row_i += 1
    ws0[f"A{row_i}"] = "分类"
    ws0[f"B{row_i}"] = "数量"
    row_i += 1
    sc = Counter(r["cat"] for r in star_rows)
    for k, v in sorted(sc.items(), key=lambda x: -x[1]):
        ws0[f"A{row_i}"] = k
        ws0[f"B{row_i}"] = v
        row_i += 1

    row_i += 1
    ws0[f"A{row_i}"] = "使用说明"
    ws0[f"A{row_i}"].font = Font(bold=True)
    notes = [
        "1. 「仓库」：自有仓 + Fork，含处理分类与建议；可用筛选按分类过滤。",
        "2. 「星标项目」：全部星标；建议取消/评估的排在前面；「建议归入List」用于建 GitHub Lists。",
        "3. 颜色：红粉=建议删除/取消；橙=建议归档；黄=需评估；绿=活跃/近期；蓝=保留；灰=已归档。",
        "4. 删除 Fork / 归档前请再确认；本表仅为建议。",
    ]
    for n in notes:
        row_i += 1
        ws0[f"A{row_i}"] = n
    ws0.column_dimensions["A"].width = 80
    ws0.column_dimensions["B"].width = 12

    ws1 = wb.create_sheet("仓库")
    repo_headers = [
        "仓库名", "完整名", "类型", "可见性", "是否归档", "主语言",
        "Stars", "描述", "创建时间", "最后推送", "距今推送天数",
        "上游仓库", "领先提交ahead", "落后behind", "本人提交(默认分支)",
        "处理分类", "建议", "URL",
    ]
    style_header(ws1, repo_headers)
    for i, row in enumerate(repo_rows, 2):
        vals = [
            row["name"], row["full"], row["type"], row["vis"], row["archived"], row["lang"],
            row["stars"], row["desc"], row["created"], row["pushed"], row["days"],
            row["parent"], row["ahead"], row["behind"], row["user_c"],
            row["cat"], row["advice"], row["url"],
        ]
        for j, v in enumerate(vals, 1):
            cell = ws1.cell(i, j, v)
            cell.alignment = wrap
            cell.border = thin
        f = row_fill(row["cat"])
        if f:
            for j in range(1, len(vals) + 1):
                ws1.cell(i, j).fill = f
    ws1.auto_filter.ref = f"A1:R{len(repo_rows)+1}"
    ws1.freeze_panes = "A2"
    autosize(ws1)
    ws1.column_dimensions["H"].width = 40
    ws1.column_dimensions["Q"].width = 55

    ws2 = wb.create_sheet("星标项目")
    star_headers = [
        "仓库", "Owner", "主语言", "Topics", "描述",
        "上游Stars", "是否归档", "是否Fork",
        "最后推送", "距今推送天数", "星标时间", "距今星标天数",
        "处理分类", "建议归入List", "建议", "URL",
    ]
    style_header(ws2, star_headers)
    for i, row in enumerate(star_rows, 2):
        vals = [
            row["repo"], row["owner"], row["lang"], row["topics"], row["desc"],
            row["stars"], row["archived"], row["fork"],
            row["pushed"], row["pdays"], row["starred"], row["sdays"],
            row["cat"], row["list"], row["advice"], row["url"],
        ]
        for j, v in enumerate(vals, 1):
            cell = ws2.cell(i, j, v)
            cell.alignment = wrap
            cell.border = thin
        f = row_fill(row["cat"])
        if f:
            for j in range(1, len(vals) + 1):
                ws2.cell(i, j).fill = f
    ws2.auto_filter.ref = f"A1:P{len(star_rows)+1}"
    ws2.freeze_panes = "A2"
    autosize(ws2)
    ws2.column_dimensions["E"].width = 40
    ws2.column_dimensions["O"].width = 55

    wb.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export GitHub organize report Excel")
    parser.add_argument(
        "--out",
        default="",
        help="Output .xlsx path (default: Desktop/GitHub整理建议_YYYYMMDD_HHMM.xlsx)",
    )
    parser.add_argument(
        "--keep",
        default="",
        help="Comma-separated fork repo names to mark as user-kept",
    )
    parser.add_argument(
        "--skip-fork-enrich",
        action="store_true",
        help="Skip per-fork compare/author API (faster, less accurate for forks)",
    )
    args = parser.parse_args()
    keep = {x.strip() for x in args.keep.split(",") if x.strip()}

    login = get_login()
    print(f"login: {login}", flush=True)

    print("fetching repos...", flush=True)
    repos = fetch_repos(login)
    forks = [r for r in repos if r.get("isFork")]
    if not args.skip_fork_enrich:
        print(f"enriching {len(forks)} forks...", flush=True)
        for i, r in enumerate(forks, 1):
            print(f"  [{i}/{len(forks)}] {r['name']}", flush=True)
            enrich_fork(login, r)
    else:
        for r in forks:
            r["_parent"] = None
            r["_ahead"] = None
            r["_behind"] = None
            r["_user_commits"] = None

    repo_rows = []
    for r in repos:
        cat, advice = classify_repo(r, keep)
        lang = r.get("primaryLanguage")
        if isinstance(lang, dict):
            lang = lang.get("name")
        repo_rows.append(
            {
                "name": r["name"],
                "full": r.get("nameWithOwner") or f"{login}/{r['name']}",
                "type": "Fork" if r.get("isFork") else "自有",
                "vis": "私有" if r.get("isPrivate") else "公开",
                "archived": "是" if r.get("isArchived") else "否",
                "lang": lang or "",
                "stars": r.get("stargazerCount") or 0,
                "desc": r.get("description") or "",
                "created": (r.get("createdAt") or "")[:10],
                "pushed": (r.get("pushedAt") or "")[:10],
                "days": days_ago(r.get("pushedAt")),
                "parent": r.get("_parent") or "",
                "ahead": r.get("_ahead") if r.get("_ahead") is not None else "",
                "behind": r.get("_behind") if r.get("_behind") is not None else "",
                "user_c": {1: "有", 0: "无", None: ""}.get(
                    r.get("_user_commits"), r.get("_user_commits")
                ),
                "cat": cat,
                "advice": advice,
                "url": r.get("url") or "",
                "_prio": REPO_PRIO.get(cat, 50),
            }
        )
    repo_rows.sort(key=lambda x: (x["_prio"], 0 if x["type"] == "Fork" else 1, -(x["days"] or 0)))

    print("fetching stars...", flush=True)
    tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp")
    stars = fetch_stars(tmp)
    star_rows = []
    for s in stars:
        cat, advice, lst = classify_star(s)
        star_rows.append(
            {
                "repo": s["nameWithOwner"],
                "owner": s.get("owner") or "",
                "lang": s.get("language") or "",
                "topics": ", ".join(s.get("topics") or []),
                "desc": s.get("description") or "",
                "stars": s.get("stargazerCount") or 0,
                "archived": "是" if s.get("isArchived") else "否",
                "fork": "是" if s.get("isFork") else "否",
                "pushed": (s.get("pushedAt") or "")[:10],
                "pdays": days_ago(s.get("pushedAt")),
                "starred": (s.get("starredAt") or "")[:10],
                "sdays": days_ago(s.get("starredAt")),
                "cat": cat,
                "list": lst,
                "advice": advice,
                "url": s.get("url") or "",
                "_prio": STAR_PRIO.get(cat, 50),
            }
        )
    star_rows.sort(key=lambda x: (x["_prio"], -(x["pdays"] or 0)))

    if args.out:
        out = Path(args.out)
    else:
        desktop = Path.home() / "Desktop"
        if not desktop.is_dir():
            desktop = Path.home() / "Documents"
        if not desktop.is_dir():
            desktop = Path.home()
        out = desktop / f"GitHub整理建议_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"writing {out} ...", flush=True)
    write_excel(out, login, repo_rows, star_rows, keep)
    print(f"OK: {out}")
    print(f"repos={len(repo_rows)} stars={len(star_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
