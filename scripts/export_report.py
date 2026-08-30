#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export GitHub organize Excel from live audit or existing audit JSON.

Usage:
  python export_report.py
  python export_report.py --from audit.json --out report.xlsx
  python export_report.py --keep a,b
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    default_output_dir,
    load_audit,
    run_audit,
    save_audit,
)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

# 人工处理列：下拉可选「按照建议」「不处理」；亦可填任意文字作「其他处理方式」
MANUAL_DEFAULT = "不处理"
MANUAL_FOLLOW = "按照建议"
MANUAL_COL = "人工处理"
RESULT_COL = "处理结果"
FURTHER_COL = "进一步建议"


def row_fill(cat: str):
    fills = {
        "建议删除": PatternFill("solid", fgColor="FCE4EC"),
        "建议清理": PatternFill("solid", fgColor="FCE4EC"),
        "建议检查": PatternFill("solid", fgColor="FCE4EC"),
        "建议归档": PatternFill("solid", fgColor="FFF3E0"),
        "建议关注": PatternFill("solid", fgColor="FFF8E1"),
        "建议评估": PatternFill("solid", fgColor="FFF8E1"),
        "建议取消": PatternFill("solid", fgColor="FCE4EC"),
        "权限不足": PatternFill("solid", fgColor="ECEFF1"),
        "活跃": PatternFill("solid", fgColor="E8F5E9"),
        "正常": PatternFill("solid", fgColor="E8F5E9"),
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


def _add_manual_validation(ws, manual_col_idx: int, nrows: int) -> None:
    """人工处理列：下拉「按照建议 / 不处理」，允许填其它文字描述。"""
    if nrows < 1:
        return
    letter = get_column_letter(manual_col_idx)
    dv = DataValidation(
        type="list",
        formula1=f'"{MANUAL_FOLLOW},{MANUAL_DEFAULT}"',
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=False,
        showInputMessage=True,
        promptTitle="人工处理",
        prompt="可选：按照建议 / 不处理；或直接填写其它处理方式文字",
    )
    dv.add(f"{letter}2:{letter}{nrows + 1}")
    ws.add_data_validation(dv)


def _write_sheet(ws, headers, rows, value_fn, filter_cols: str, manual_col_idx: int | None = None):
    wrap = Alignment(wrap_text=True, vertical="top")
    thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )
    style_header(ws, headers)
    for i, row in enumerate(rows, 2):
        vals = value_fn(row)
        for j, v in enumerate(vals, 1):
            cell = ws.cell(i, j, v)
            cell.alignment = wrap
            cell.border = thin
        f = row_fill(row.get("cat", ""))
        if f:
            # 人工处理/结果/建议列保持白底便于填写
            end = (manual_col_idx - 1) if manual_col_idx else len(vals)
            for j in range(1, end + 1):
                ws.cell(i, j).fill = f
    if rows:
        ws.auto_filter.ref = f"A1:{filter_cols}{len(rows)+1}"
    ws.freeze_panes = "A2"
    if manual_col_idx and rows:
        _add_manual_validation(ws, manual_col_idx, len(rows))
    autosize(ws)


def write_excel(
    out: Path,
    login: str,
    repo_rows: list,
    star_rows: list,
    hygiene_rows: list,
    keep: set[str],
) -> None:
    wb = Workbook()

    ws0 = wb.active
    ws0.title = "汇总说明"
    ws0["A1"] = f"GitHub 整理建议（{login}）"
    ws0["A1"].font = Font(bold=True, size=14)
    ws0["A2"] = f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    own_n = sum(1 for r in repo_rows if r["type"] == "自有")
    fork_n = sum(1 for r in repo_rows if r["type"] == "Fork")
    ws0["A3"] = f"仓库总数: {len(repo_rows)}（自有 {own_n} / Fork {fork_n}）"
    ws0["A4"] = f"星标总数: {len(star_rows)}"
    ws0["A5"] = f"工作流/密钥审计仓数: {len(hygiene_rows)}"
    if keep:
        ws0["A6"] = "指定保留 Fork: " + ", ".join(sorted(keep))

    row_i = 8
    for title, counter in [
        ("仓库处理分类统计", Counter(r["cat"] for r in repo_rows)),
        ("星标处理分类统计", Counter(r["cat"] for r in star_rows)),
        ("工作流与密钥分类统计", Counter(r["cat"] for r in hygiene_rows)),
    ]:
        ws0[f"A{row_i}"] = title
        ws0[f"A{row_i}"].font = Font(bold=True)
        row_i += 1
        ws0[f"A{row_i}"] = "分类"
        ws0[f"B{row_i}"] = "数量"
        row_i += 1
        for k, v in sorted(counter.items(), key=lambda x: -x[1]):
            ws0[f"A{row_i}"] = k
            ws0[f"B{row_i}"] = v
            row_i += 1
        row_i += 1

    ws0[f"A{row_i}"] = "使用说明"
    ws0[f"A{row_i}"].font = Font(bold=True)
    for n in [
        "1. 「仓库」：自有仓 + Fork，含处理分类与建议。",
        "2. 「星标项目」：全部星标；「建议归入List」用于建 GitHub Lists。",
        "3. 「工作流与密钥」：自有仓的 Actions 失败、疑似孤儿 Secret、CodeQL 状态。",
        "4. 孤儿密钥=仓库 Secrets 列表中存在，但未在 .github/workflows 文本中以 secrets.NAME 引用。",
        "5. 颜色：红粉=建议删除/清理/检查；橙=归档；黄=关注/评估；绿=正常/活跃；灰=已归档/权限不足。",
        "6. 删除密钥或改 Settings 前请再确认；本表仅为建议。",
        "7. 「人工处理」列（默认「不处理」）：可选「按照建议」；或填写其它处理方式文字。填完后可用 process_excel.py 回写「处理结果」。",
        "8. 「处理结果」「进一步建议」在导出时为空；执行 process_excel.py 后自动填写。",
    ]:
        row_i += 1
        ws0[f"A{row_i}"] = n
    ws0.column_dimensions["A"].width = 90
    ws0.column_dimensions["B"].width = 12

    # 仓库：原 18 列 + 人工处理/处理结果/进一步建议 → U
    ws1 = wb.create_sheet("仓库")
    repo_headers = [
        "仓库名", "完整名", "类型", "可见性", "是否归档", "主语言",
        "Stars", "描述", "创建时间", "最后推送", "距今推送天数",
        "上游仓库", "领先提交ahead", "落后behind", "本人提交(默认分支)",
        "处理分类", "建议", "URL",
        MANUAL_COL, RESULT_COL, FURTHER_COL,
    ]
    _write_sheet(
        ws1,
        repo_headers,
        repo_rows,
        lambda row: [
            row["name"], row["full"], row["type"], row["vis"], row["archived"], row["lang"],
            row["stars"], row["desc"], row["created"], row["pushed"], row["days"],
            row["parent"], row["ahead"], row["behind"], row["user_c"],
            row["cat"], row["advice"], row["url"],
            MANUAL_DEFAULT, "", "",
        ],
        "U",
        manual_col_idx=19,
    )
    ws1.column_dimensions["H"].width = 40
    ws1.column_dimensions["Q"].width = 55
    ws1.column_dimensions["S"].width = 16
    ws1.column_dimensions["T"].width = 36
    ws1.column_dimensions["U"].width = 40

    # 星标：原 16 列 + 3 → S
    ws2 = wb.create_sheet("星标项目")
    star_headers = [
        "仓库", "Owner", "主语言", "Topics", "描述",
        "上游Stars", "是否归档", "是否Fork",
        "最后推送", "距今推送天数", "星标时间", "距今星标天数",
        "处理分类", "建议归入List", "建议", "URL",
        MANUAL_COL, RESULT_COL, FURTHER_COL,
    ]
    _write_sheet(
        ws2,
        star_headers,
        star_rows,
        lambda row: [
            row["repo"], row["owner"], row["lang"], row["topics"], row["desc"],
            row["stars"], row["archived"], row["fork"],
            row["pushed"], row["pdays"], row["starred"], row["sdays"],
            row["cat"], row["list"], row["advice"], row["url"],
            MANUAL_DEFAULT, "", "",
        ],
        "S",
        manual_col_idx=17,
    )
    ws2.column_dimensions["E"].width = 40
    ws2.column_dimensions["O"].width = 55
    ws2.column_dimensions["Q"].width = 16
    ws2.column_dimensions["R"].width = 36
    ws2.column_dimensions["S"].width = 40

    # 工作流：原 14 列 + 3 → Q
    ws3 = wb.create_sheet("工作流与密钥")
    hygiene_headers = [
        "仓库", "是否归档", "有Workflow", "Workflow数",
        "近期失败运行数", "失败工作流名",
        "Secrets数", "孤儿Secrets数", "孤儿Secrets列表",
        "CodeQL状态", "处理分类", "建议", "备注/错误", "URL",
        MANUAL_COL, RESULT_COL, FURTHER_COL,
    ]
    _write_sheet(
        ws3,
        hygiene_headers,
        hygiene_rows,
        lambda row: [
            row.get("full"), row.get("archived"), row.get("has_workflows"), row.get("workflow_count"),
            row.get("failed_runs_30d"), row.get("failed_workflow_names"),
            row.get("secret_count"), row.get("orphan_secret_count"), row.get("orphan_secrets"),
            row.get("codeql"), row.get("cat"), row.get("advice"), row.get("error"), row.get("url"),
            MANUAL_DEFAULT, "", "",
        ],
        "Q",
        manual_col_idx=15,
    )
    ws3.column_dimensions["F"].width = 36
    ws3.column_dimensions["I"].width = 36
    ws3.column_dimensions["L"].width = 55
    ws3.column_dimensions["O"].width = 16
    ws3.column_dimensions["P"].width = 36
    ws3.column_dimensions["Q"].width = 40

    wb.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export GitHub organize report Excel")
    parser.add_argument("--from", dest="src", default="", help="Existing audit JSON from audit.py")
    parser.add_argument("--out", default="", help="Output .xlsx path")
    parser.add_argument("--audit-out", default="", help="Also save audit JSON when running live audit")
    parser.add_argument("--keep", default="", help="Comma-separated fork names to keep")
    parser.add_argument("--skip-fork-enrich", action="store_true")
    parser.add_argument("--skip-stars", action="store_true")
    parser.add_argument(
        "--with-hygiene",
        action="store_true",
        help="Include workflow/secrets audit (default: off)",
    )
    parser.add_argument(
        "--skip-hygiene",
        action="store_true",
        help=argparse.SUPPRESS,  # 兼容旧参数；hygiene 本就默认跳过
    )
    parser.add_argument("--hygiene-include-archived", action="store_true")
    args = parser.parse_args()
    keep = {x.strip() for x in args.keep.split(",") if x.strip()}

    if args.src:
        audit = load_audit(Path(args.src))
        if keep:
            print("note: --keep ignored when --from is set (use keep at audit time)", flush=True)
        login = audit["summary"]["login"]
        repo_rows = audit["repos"]
        star_rows = audit["stars"]
        hygiene_rows = audit.get("hygiene") or []
        keep = set(audit["summary"].get("keep") or [])
    else:
        audit = run_audit(
            keep,
            skip_fork_enrich=args.skip_fork_enrich,
            skip_stars=args.skip_stars,
            skip_hygiene=not args.with_hygiene,
            hygiene_include_archived=args.hygiene_include_archived,
            progress=True,
        )
        login = audit["summary"]["login"]
        repo_rows = audit["repos"]
        star_rows = audit["stars"]
        hygiene_rows = audit.get("hygiene") or []
        if args.audit_out:
            save_audit(audit, Path(args.audit_out))
            print(f"audit json: {args.audit_out}", flush=True)

    out = Path(args.out) if args.out else (
        default_output_dir() / f"GitHub整理建议_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"writing {out} ...", flush=True)
    write_excel(out, login, repo_rows, star_rows, hygiene_rows, keep)
    print(f"OK: {out}")
    print(f"repos={len(repo_rows)} stars={len(star_rows)} hygiene={len(hygiene_rows)}")
    print(
        "提示: 可在各表「人工处理」列填写「按照建议」/「不处理」(默认)/其它文字；"
        "填完后用 process_excel.py --from <本文件> --dry-run 再 --yes 回写处理结果。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
