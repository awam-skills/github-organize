#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub organize — shared detection, classification, fetch helpers.

Requires: gh (authenticated), Python 3.9+
"""
from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

DELETE_FORK_CATEGORIES = {
    "建议删除-无新提交",
    "建议评估后删除",
}

ARCHIVE_OWN_CATEGORIES = {
    "建议归档-长期未更新",
}

UNSTAR_CATEGORIES = {
    "建议取消星标-上游已归档",
    "建议评估取消-长期未更新",
}


def run_gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:4])}... failed: {(r.stderr or r.stdout).strip()}")
    return r


def run_gh_text(args: list[str]) -> str:
    return run_gh(args, check=True).stdout


def days_ago(iso: str | None) -> int | None:
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (NOW - dt).days


def tmp_dir() -> Path:
    return Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp")


def skill_dir() -> Path:
    """本技能根目录（scripts/ 的上一级）。"""
    return Path(__file__).resolve().parent.parent


def default_output_dir() -> Path:
    """默认产物目录：技能下的 output/（自动创建）。"""
    out = skill_dir() / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def get_login() -> str:
    return json.loads(run_gh_text(["api", "user", "--jq", "{login:.login}"]))["login"]


def auth_scopes() -> list[str]:
    """Best-effort parse of `gh auth status` scopes."""
    r = run_gh(["auth", "status"], check=False)
    text = (r.stdout or "") + (r.stderr or "")
    for line in text.splitlines():
        if "Token scopes:" in line or "token scopes:" in line.lower():
            # e.g. - Token scopes: 'delete_repo', 'gist', 'repo'
            part = line.split(":", 1)[-1]
            return [s.strip().strip("'\"") for s in part.replace("'", "").split(",") if s.strip()]
    return []


def fetch_repos(login: str) -> list[dict]:
    return json.loads(
        run_gh_text(
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
    """Fill _parent, _ahead, _behind, _user_commits, _compare_error, _fork_branch."""
    name = repo["name"]
    full = f"{login}/{name}"
    repo["_compare_error"] = None
    repo["_fork_branch"] = None
    repo["_parent_branch"] = None

    detail_r = run_gh(
        [
            "api",
            f"repos/{full}",
            "--jq",
            "{parent:.parent.full_name,parent_default:.parent.default_branch,"
            "default:.default_branch}",
        ],
        check=False,
    )
    if detail_r.returncode != 0:
        repo["_parent"] = None
        repo["_ahead"] = None
        repo["_behind"] = None
        repo["_user_commits"] = None
        repo["_compare_error"] = (detail_r.stderr or detail_r.stdout or "").strip()[:200]
        return

    detail = json.loads(detail_r.stdout)
    parent = detail.get("parent")
    repo["_parent"] = parent
    fork_branch = detail.get("default") or "main"
    parent_branch = detail.get("parent_default") or "main"
    repo["_fork_branch"] = fork_branch

    if parent:
        parent_owner = parent.split("/")[0]
        br = run_gh(["api", f"repos/{parent}/branches/{fork_branch}"], check=False)
        if br.returncode == 0:
            parent_branch = fork_branch
        repo["_parent_branch"] = parent_branch

        base = f"{parent_owner}:{parent_branch}"
        head = f"{login}:{fork_branch}"
        encoded = f"{base.replace(':', '%3A')}...{head.replace(':', '%3A')}"
        cmp_r = run_gh(
            ["api", f"repos/{full}/compare/{encoded}", "--jq", "{ahead_by,behind_by,status}"],
            check=False,
        )
        if cmp_r.returncode == 0:
            cmp_ = json.loads(cmp_r.stdout)
            repo["_ahead"] = cmp_.get("ahead_by")
            repo["_behind"] = cmp_.get("behind_by")
            repo["_compare_status"] = cmp_.get("status")
        else:
            repo["_ahead"] = None
            repo["_behind"] = None
            repo["_compare_error"] = (cmp_r.stderr or cmp_r.stdout or "").strip()[:200]
    else:
        repo["_ahead"] = None
        repo["_behind"] = None

    commits_r = run_gh(
        ["api", f"repos/{full}/commits?author={login}&per_page=1"],
        check=False,
    )
    if commits_r.returncode == 0:
        body = (commits_r.stdout or "").strip()
        if body in ("", "[]"):
            repo["_user_commits"] = 0
        else:
            arr = json.loads(body)
            repo["_user_commits"] = 1 if arr else 0
    else:
        err = ((commits_r.stderr or "") + (commits_r.stdout or "")).lower()
        if "empty" in err or "409" in err:
            repo["_user_commits"] = 0
        else:
            repo["_user_commits"] = None
            if not repo.get("_compare_error"):
                repo["_compare_error"] = (commits_r.stderr or commits_r.stdout or "").strip()[:200]


def classify_repo(r: dict, keep: set[str]) -> tuple[str, str]:
    name = r["name"]
    d = days_ago(r.get("pushedAt"))
    is_fork = r.get("isFork")
    archived = r.get("isArchived")
    desc = (r.get("description") or "").strip()
    stars = r.get("stargazerCount") or 0
    user_c = r.get("_user_commits")
    ahead = r.get("_ahead")
    cmp_err = r.get("_compare_error")

    if is_fork:
        if name in keep:
            return "保留-你指定保留", "继续保留；若只作参考可读，可考虑取消 fork 关系改收藏上游。"
        if d is not None and d <= 180 and user_c == 1:
            return "保留-近期在用", "有近期活动或本人提交，建议保留；重要改动可考虑独立成仓或向上游提 PR。"
        if user_c == 0 and ahead == 0:
            return "建议删除-无新提交", "相对上游无领先提交且默认分支无本人 commit；删除前给上游打星（若未星标）。"
        if user_c == 0 and ahead is None:
            tip = "默认分支无本人 commit"
            if cmp_err:
                tip += f"；上游比对失败（{cmp_err[:80]}）"
            else:
                tip += "且无法确认 ahead（按无新提交处理）"
            tip += "；删除前给上游打星。"
            return "建议删除-无新提交", tip
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


def fetch_stars(progress: bool = True) -> list[dict]:
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
    qpath = tmp_dir() / "github-organize-stars.graphql"
    qpath.write_text(query, encoding="utf-8")
    stars: list[dict] = []
    cursor = None
    while True:
        args = ["api", "graphql", "-F", f"query=@{qpath}"]
        if cursor:
            args += ["-f", f"cursor={cursor}"]
        data = json.loads(run_gh_text(args))
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
        if progress:
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
        return (
            "建议评估取消-长期未更新",
            f"上游超过约 3 年未推送（{d} 天）；过时技术栈可 unstar。建议列表：{lst}",
            lst,
        )
    if d is not None and d > 365 * 2:
        return (
            "可保留但标为过时",
            f"约 2–3 年未更新；若仍有参考价值保留并放入「已过时」列表。建议列表：{lst}",
            lst,
        )
    if starred_days is not None and starred_days <= 90:
        return "近期星标-保留并归类", f"近 90 天内星标；优先归入 Lists。建议列表：{lst}", lst
    if d is not None and d <= 365:
        return "保留-上游仍活跃", f"上游一年内有更新；保留并归入 Lists。建议列表：{lst}", lst
    return "保留-一般参考", f"可保留；整理时归入 Lists。建议列表：{lst}", lst


def build_repo_row(login: str, r: dict, keep: set[str]) -> dict:
    cat, advice = classify_repo(r, keep)
    lang = r.get("primaryLanguage")
    if isinstance(lang, dict):
        lang = lang.get("name")
    return {
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
        "user_c": {1: "有", 0: "无", None: ""}.get(r.get("_user_commits"), r.get("_user_commits")),
        "compare_error": r.get("_compare_error") or "",
        "cat": cat,
        "advice": advice,
        "url": r.get("url") or "",
        "_prio": REPO_PRIO.get(cat, 50),
    }


def build_star_row(s: dict) -> dict:
    cat, advice, lst = classify_star(s)
    return {
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


HYGIENE_PRIO = {
    "建议检查-工作流失败": 0,
    "建议清理-疑似孤儿密钥": 1,
    "建议关注-有密钥无工作流": 2,
    "建议关注-CodeQL未配置": 3,
    "权限不足-跳过密钥": 4,
    "正常": 9,
    "已归档-跳过": 10,
}


def _workflow_text_blob(full: str) -> tuple[int, str]:
    """Return (file_count, concatenated workflow file texts)."""
    import base64
    import re

    listing = run_gh(["api", f"repos/{full}/contents/.github/workflows"], check=False)
    if listing.returncode != 0:
        return 0, ""
    try:
        items = json.loads(listing.stdout)
    except Exception:
        return 0, ""
    if not isinstance(items, list):
        return 0, ""
    texts: list[str] = []
    count = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name") or ""
        if not (name.endswith(".yml") or name.endswith(".yaml")):
            continue
        path = it.get("path")
        if not path:
            continue
        count += 1
        fr = run_gh(["api", f"repos/{full}/contents/{path}"], check=False)
        if fr.returncode != 0:
            continue
        try:
            meta = json.loads(fr.stdout)
            content = meta.get("content") or ""
            content = re.sub(r"\s+", "", content)
            body = base64.b64decode(content).decode("utf-8", errors="replace")
            texts.append(body)
        except Exception:
            continue
    return count, "\n".join(texts)


def _secret_referenced(name: str, blob: str) -> bool:
    if not name or not blob:
        return False
    patterns = (
        f"secrets.{name}",
        f"secrets['{name}']",
        f'secrets["{name}"]',
        f"secrets.{name.lower()}",  # unlikely but cheap
    )
    return any(p in blob for p in patterns)


def audit_one_repo_hygiene(full: str, *, archived: bool = False) -> dict:
    """Workflow + Actions secrets + light CodeQL check for one owned repo."""
    row: dict[str, Any] = {
        "full": full,
        "name": full.split("/")[-1],
        "archived": "是" if archived else "否",
        "has_workflows": "否",
        "workflow_count": 0,
        "failed_runs_30d": 0,
        "failed_workflow_names": "",
        "secret_count": 0,
        "orphan_secret_count": 0,
        "orphan_secrets": "",
        "codeql": "",
        "cat": "正常",
        "advice": "未见明显工作流/密钥问题。",
        "url": f"https://github.com/{full}",
        "error": "",
        "_prio": HYGIENE_PRIO["正常"],
    }
    if archived:
        row["cat"] = "已归档-跳过"
        row["advice"] = "已归档仓库默认不深入审计工作流与密钥。"
        row["_prio"] = HYGIENE_PRIO["已归档-跳过"]
        return row

    # Workflows list
    wf = run_gh(
        ["api", f"repos/{full}/actions/workflows", "--jq", "{total:.total_count,names:[.workflows[].name]}"],
        check=False,
    )
    workflow_names: list[str] = []
    if wf.returncode == 0:
        try:
            data = json.loads(wf.stdout)
            row["workflow_count"] = data.get("total") or 0
            workflow_names = data.get("names") or []
            row["has_workflows"] = "是" if row["workflow_count"] else "否"
        except Exception as e:
            row["error"] = f"workflows_parse:{e}"
    else:
        err = (wf.stderr or wf.stdout or "").strip()[:120]
        row["error"] = f"workflows:{err}"

    # Recent failures (last ~30 days window approximated by fetching recent failures)
    fail = run_gh(
        [
            "api",
            f"repos/{full}/actions/runs?status=failure&per_page=20",
            "--jq",
            "{count:(.workflow_runs|length),names:[.workflow_runs[].name]}",
        ],
        check=False,
    )
    failed_names: list[str] = []
    if fail.returncode == 0:
        try:
            fd = json.loads(fail.stdout)
            # Deduplicate names; count unique recent failures listed
            failed_names = list(dict.fromkeys(fd.get("names") or []))
            row["failed_runs_30d"] = fd.get("count") or 0
            row["failed_workflow_names"] = ", ".join(failed_names[:8])
        except Exception:
            pass

    # Secrets + orphan detection
    sec = run_gh(
        ["api", f"repos/{full}/actions/secrets", "--jq", "{count:.total_count,names:[.secrets[].name]}"],
        check=False,
    )
    secret_names: list[str] = []
    secrets_denied = False
    if sec.returncode == 0:
        try:
            sd = json.loads(sec.stdout)
            secret_names = sd.get("names") or []
            row["secret_count"] = sd.get("count") or len(secret_names)
        except Exception as e:
            row["error"] = (row["error"] + f";secrets_parse:{e}").strip(";")
    else:
        err = (sec.stderr or sec.stdout or "").lower()
        if "403" in err or "not found" in err or "404" in err:
            secrets_denied = True
            row["error"] = (row["error"] + ";secrets:no_admin_or_disabled").strip(";")
        else:
            row["error"] = (row["error"] + f";secrets:{(sec.stderr or sec.stdout or '')[:80]}").strip(";")

    orphans: list[str] = []
    if secret_names:
        _wf_files, blob = _workflow_text_blob(full)
        # Also include workflow names from API as weak signal — orphans need file text
        for name in secret_names:
            if not _secret_referenced(name, blob):
                orphans.append(name)
        row["orphan_secret_count"] = len(orphans)
        row["orphan_secrets"] = ", ".join(orphans)

    # CodeQL default setup (best-effort)
    cq = run_gh(
        ["api", f"repos/{full}/code-scanning/default-setup", "--jq", ".state // .message // ."],
        check=False,
    )
    if cq.returncode == 0:
        state = (cq.stdout or "").strip().strip('"')
        row["codeql"] = state[:80] or "unknown"
    else:
        msg = (cq.stderr or cq.stdout or "").strip()
        if "Advanced Security must be enabled" in msg or "403" in msg:
            row["codeql"] = "不可用/未开通"
        elif "404" in msg:
            row["codeql"] = "未配置"
        else:
            row["codeql"] = "查询失败"

    # Classification
    if row["failed_runs_30d"] and row["failed_runs_30d"] > 0:
        row["cat"] = "建议检查-工作流失败"
        row["advice"] = (
            f"近期有 {row['failed_runs_30d']} 条失败的 Actions 运行"
            + (f"（{row['failed_workflow_names']}）" if row["failed_workflow_names"] else "")
            + "；建议打开 Actions 排查或禁用无用 workflow。"
        )
    elif orphans:
        row["cat"] = "建议清理-疑似孤儿密钥"
        row["advice"] = (
            f"发现 {len(orphans)} 个疑似未被 workflow 引用的 Actions Secret"
            f"（{', '.join(orphans[:6])}）；确认无外部用途后可删除。"
        )
    elif row["secret_count"] and row["has_workflows"] == "否":
        row["cat"] = "建议关注-有密钥无工作流"
        row["advice"] = "仓库有 Actions Secret 但未见 workflow；可能是遗留配置，确认后清理密钥或补回 workflow。"
    elif secrets_denied and row["has_workflows"] == "是":
        row["cat"] = "权限不足-跳过密钥"
        row["advice"] = "无法读取 secrets（需 admin）；工作流侧可正常查看。如需孤儿密钥审计请提升权限。"
    elif row["codeql"] in ("未配置", "NotFound", "null") and row["has_workflows"] == "是":
        row["cat"] = "建议关注-CodeQL未配置"
        row["advice"] = "存在 Actions 但 CodeQL default setup 似乎未启用；按需在 Security 中配置。"
    else:
        row["cat"] = "正常"
        tips = []
        if row["has_workflows"] == "否" and not row["secret_count"]:
            tips.append("无 Actions / 无仓库级 Secret（常见于纯代码仓）。")
        row["advice"] = "；".join(tips) if tips else "未见明显工作流/密钥问题。"

    row["_prio"] = HYGIENE_PRIO.get(row["cat"], 50)
    return row


def audit_hygiene(
    login: str,
    repos: list[dict],
    *,
    include_archived: bool = False,
    include_forks: bool = False,
    progress: bool = True,
) -> list[dict]:
    """Audit workflows/secrets for owned repos (skips forks by default)."""
    targets = []
    for r in repos:
        if r.get("isFork") and not include_forks:
            continue
        if r.get("isArchived") and not include_archived:
            continue
        targets.append(r)

    rows: list[dict] = []
    for i, r in enumerate(targets, 1):
        full = r.get("nameWithOwner") or f"{login}/{r['name']}"
        if progress:
            print(f"  hygiene [{i}/{len(targets)}] {full}", flush=True)
        rows.append(audit_one_repo_hygiene(full, archived=bool(r.get("isArchived"))))
    rows.sort(key=lambda x: (x.get("_prio", 50), -(x.get("failed_runs_30d") or 0), -(x.get("orphan_secret_count") or 0)))
    return rows


def run_audit(
    keep: set[str] | None = None,
    *,
    skip_fork_enrich: bool = False,
    skip_stars: bool = False,
    skip_hygiene: bool = True,
    hygiene_include_archived: bool = False,
    progress: bool = True,
) -> dict[str, Any]:
    """Full detection pipeline. Returns serializable audit dict.

    默认跳过 workflow/secrets（hygiene）；需显式 skip_hygiene=False 才启用。
    """
    keep = keep or set()
    login = get_login()
    if progress:
        print(f"login: {login}", flush=True)

    if progress:
        print("fetching repos...", flush=True)
    repos = fetch_repos(login)
    forks = [r for r in repos if r.get("isFork")]

    if not skip_fork_enrich:
        if progress:
            print(f"enriching {len(forks)} forks...", flush=True)
        for i, r in enumerate(forks, 1):
            if progress:
                print(f"  [{i}/{len(forks)}] {r['name']}", flush=True)
            enrich_fork(login, r)
    else:
        for r in forks:
            r["_parent"] = None
            r["_ahead"] = None
            r["_behind"] = None
            r["_user_commits"] = None
            r["_compare_error"] = "skipped"

    repo_rows = [build_repo_row(login, r, keep) for r in repos]
    repo_rows.sort(
        key=lambda x: (x["_prio"], 0 if x["type"] == "Fork" else 1, -(x["days"] or 0))
    )

    star_rows: list[dict] = []
    if not skip_stars:
        if progress:
            print("fetching stars...", flush=True)
        stars = fetch_stars(progress=progress)
        star_rows = [build_star_row(s) for s in stars]
        star_rows.sort(key=lambda x: (x["_prio"], -(x["pdays"] or 0)))

    hygiene_rows: list[dict] = []
    if not skip_hygiene:
        if progress:
            print("auditing workflows & secrets (own repos)...", flush=True)
        hygiene_rows = audit_hygiene(
            login,
            repos,
            include_archived=hygiene_include_archived,
            progress=progress,
        )

    summary = {
        "login": login,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "keep": sorted(keep),
        "repo_total": len(repo_rows),
        "own_total": sum(1 for r in repo_rows if r["type"] == "自有"),
        "fork_total": sum(1 for r in repo_rows if r["type"] == "Fork"),
        "star_total": len(star_rows),
        "hygiene_total": len(hygiene_rows),
        "hygiene_skipped": skip_hygiene,
        "stars_skipped": skip_stars,
        "repo_by_cat": dict(Counter(r["cat"] for r in repo_rows)),
        "star_by_cat": dict(Counter(r["cat"] for r in star_rows)),
        "hygiene_by_cat": dict(Counter(r["cat"] for r in hygiene_rows)),
        "forks_suggest_delete": [
            {"name": r["name"], "full": r["full"], "parent": r["parent"], "cat": r["cat"]}
            for r in repo_rows
            if r["type"] == "Fork" and r["cat"] in DELETE_FORK_CATEGORIES
        ],
        "own_suggest_archive": [
            {"name": r["name"], "full": r["full"], "cat": r["cat"], "pushed": r["pushed"]}
            for r in repo_rows
            if r["type"] == "自有" and r["cat"] in ARCHIVE_OWN_CATEGORIES
        ],
        "stars_suggest_unstar": [
            {"repo": r["repo"], "cat": r["cat"], "list": r["list"]}
            for r in star_rows
            if r["cat"] in UNSTAR_CATEGORIES
        ],
        "hygiene_attention": [
            {
                "full": r["full"],
                "cat": r["cat"],
                "failed_runs": r.get("failed_runs_30d"),
                "orphan_secrets": r.get("orphan_secrets"),
            }
            for r in hygiene_rows
            if r["cat"] not in ("正常", "已归档-跳过")
        ],
    }

    return {
        "summary": summary,
        "repos": repo_rows,
        "stars": star_rows,
        "hygiene": hygiene_rows,
    }


def save_audit(audit: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # drop internal sort keys for cleaner JSON? keep them for export reuse
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


def load_audit(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_starred(parent: str) -> str:
    """Star upstream if not already. Returns already_starred|starred|failed:..."""
    if not parent or "/" not in parent:
        return "skipped:no_parent"
    check = run_gh(["api", "-X", "GET", f"user/starred/{parent}", "--silent"], check=False)
    if check.returncode == 0:
        return "already_starred"
    star = run_gh(["api", "-X", "PUT", f"user/starred/{parent}", "--silent"], check=False)
    if star.returncode == 0:
        return "starred"
    return f"failed:{(star.stderr or star.stdout or '').strip()[:120]}"


def delete_repo(full_name: str) -> str:
    r = run_gh(["repo", "delete", full_name, "--yes"], check=False)
    if r.returncode == 0:
        return "deleted"
    err = (r.stderr or r.stdout or "").strip()
    if "delete_repo" in err:
        return "failed:need_delete_repo_scope"
    return f"failed:{err[:200]}"


def archive_repo(full_name: str) -> str:
    r = run_gh(
        ["api", "-X", "PATCH", f"repos/{full_name}", "-f", "archived=true", "--silent"],
        check=False,
    )
    if r.returncode == 0:
        return "archived"
    return f"failed:{(r.stderr or r.stdout or '').strip()[:200]}"


def unstar_repo(full_name: str) -> str:
    r = run_gh(["api", "-X", "DELETE", f"user/starred/{full_name}", "--silent"], check=False)
    if r.returncode == 0:
        return "unstarred"
    return f"failed:{(r.stderr or r.stdout or '').strip()[:200]}"
