---
name: github-organize
description: >-
  审计并整理个人 GitHub 仓库与星标：找出无新提交的 fork、建议归档的自有仓、
  可取消/归类的星标；并审计自有仓 Actions 失败与疑似孤儿 Secrets，导出含
  「仓库」「星标项目」「工作流与密钥」及「人工处理」列的 Excel。可按填好的
  Excel 自动执行可处理项，不可自动项由 AI 归类并给出进一步建议后回写处理结果。
  检测逻辑优先跑 scripts/audit.py。在用户提到 GitHub 整理、清理 fork、整理星标、
  归档仓库、workflow/secrets 审计、导出 GitHub Excel、按 Excel 处理、github-organize
  时使用。
---

# GitHub 整理（仓库 + 星标 + 工作流/密钥）

**检测与分类一律用本技能脚本实现**；Agent 负责解读结果、向用户确认、再调用 `apply.py` 或 `process_excel.py` 执行。

## 脚本一览

路径相对本技能目录 `scripts/`：

| 脚本 | 作用 |
|------|------|
| [`common.py`](scripts/common.py) | 拉取 / 比对 / 分类 / **workflow·secrets 审计** |
| [`audit.py`](scripts/audit.py) | **检测入口**：输出审计 JSON + 摘要 |
| [`export_report.py`](scripts/export_report.py) | 检测或读 JSON → Excel（含人工处理列） |
| [`process_excel.py`](scripts/process_excel.py) | **按 Excel 人工处理列执行** → 回写处理结果 |
| [`apply.py`](scripts/apply.py) | 确认后：星标上游、删 fork、归档、取消星标（按 audit JSON） |

分类细则见 [reference.md](reference.md)。

## 前置条件

```bash
gh auth status
```

- 删除仓库需要 `delete_repo`：`gh auth refresh -h github.com -s delete_repo`
- 读取仓库 Secrets 需要对该仓有 **admin**（否则密钥审计会标「权限不足」）
- Excel 需要 `openpyxl`（`export_report.py` / `process_excel.py` 会尝试自动安装）

`SKILL_DIR` = 技能根目录，例如 `$HOME/.agents/skills/github-organize`

默认产物目录：`$SKILL_DIR/output/`（`audit.py` / `export_report.py` 未指定 `--out` 时写入此处；`output/` 已 gitignore，不入代码归档）。

## 进度清单

```
GitHub 整理进度:
- [ ] 1. gh auth status
- [ ] 2. 运行 audit.py（含 hygiene，除非 --skip-hygiene）
- [ ] 3. 根据 summary 汇报（含 hygiene_attention）
- [ ] 4. （可选）export_report.py 导出 Excel
- [ ] 5. 提示用户：可在各表「人工处理」列逐行填写后，用 process_excel.py 回写处理
- [ ] 6. （可选）用户填完 Excel 后 process_excel.py --dry-run → --yes
- [ ] 7. （可选）对「需AI分析 / 不可自动」行：Agent 归类并给出进一步建议
- [ ] 8. （可选）用户确认后 apply.py --dry-run → --yes（按 JSON 批量，与 Excel 流程二选一即可）
```

## 强制规则：检测走代码

1. **禁止**用临时 shell/Node 重写 fork 比对、星标分页、workflow/secrets 审计、分类规则。
2. **必须**调用 `audit.py` 或 `export_report.py`。
3. 汇报优先用 `summary`：`forks_suggest_delete` / `own_suggest_archive` / `stars_suggest_unstar` / **`hygiene_attention`**。
4. 破坏性操作**只能**经 `apply.py` 或 `process_excel.py`，且先 `--dry-run`，确认后再 `--yes`。密钥删除默认不自动执行。

## 工作流

### 1. 审计

```bash
python "$SKILL_DIR/scripts/audit.py" --keep "fork1,fork2"
```

参数：`--keep` / `--out` / `--skip-stars` / `--skip-fork-enrich` / **`--skip-hygiene`** / `--hygiene-include-archived`

### 2. 汇报

关注 `hygiene_attention`（工作流失败、孤儿密钥等）与 `hygiene_by_cat`。

### 3. 导出 Excel

```bash
python "$SKILL_DIR/scripts/export_report.py" --keep "a,b" --audit-out audit.json
python "$SKILL_DIR/scripts/export_report.py" --from audit.json --out report.xlsx
```

标签页：**汇总说明** / **仓库** / **星标项目** / **工作流与密钥**

每张数据表含列：**人工处理**（默认「不处理」）、**处理结果**、**进一步建议**。

导出成功后，**必须提示用户**：

> 已导出 Excel。你可以在「仓库 / 星标项目 / 工作流与密钥」各表的「人工处理」列按行填写：
> - **按照建议**：采纳该行「处理分类 / 建议」中可自动执行的动作
> - **不处理**（默认）：跳过
> - **其他处理方式**：直接写文字说明（如「只星标上游不删」「归档并改 description」）
>
> 填完后把文件路径发我，可运行 `process_excel.py`：能自动的自动处理，不能自动的会归类并写入「进一步建议」，再由我解读给出下一步。

### 4. 按 Excel 处理（填完人工处理后）

```bash
python "$SKILL_DIR/scripts/process_excel.py" --from report.xlsx --dry-run
python "$SKILL_DIR/scripts/process_excel.py" --from report.xlsx --yes --out result.xlsx
```

- 先 `--dry-run`，把将执行项与「需 AI / 不可自动」项汇报给用户，确认后再 `--yes`
- 脚本回写 Excel：**处理结果**、**进一步建议**；stdout 输出 JSON 摘要（含 `needs_ai`）
- Agent 对 `needs_ai` / 处理结果为「需AI分析」「不可自动」的行：根据人工处理文字与行内上下文**归类意图**，给出可执行的进一步建议（密钥/CI/Lists 等仍不擅自破坏性操作）
- 处理完成后把结果 Excel 路径与摘要返回用户

可自动映射（「按照建议」或可识别文字）：

| 表 | 条件 | 自动动作 |
|----|------|----------|
| 仓库 | Fork + 建议删除类 | 星标上游 + 删 fork |
| 仓库 | 自有 + 建议归档类 | 归档 |
| 星标 | 建议取消星标类 | unstar |
| 工作流与密钥 | 任意 | **不自动**删密钥/改 CI；写入进一步建议 |

### 5. 按 audit JSON 执行（仅确认后，与步骤 4 二选一）

`apply.py --delete-forks --star-parents` 等。孤儿密钥请人工在 Settings 删除（除非用户另行明确要求自动化）。

## 安全规则

- 删除 / 归档 / 批量 unstar：必须用户明确确认
- 「除了 X 其他都删」→ `--exclude` / `--keep` 严格保留
- 不要改 git config
- Excel「人工处理」为「不处理」或空 → 一律跳过

## 与其它技能

- 通用 issue/PR/CI：`github` 技能
- 本技能：仓卫生 + 星标 + workflow/secrets + Excel + 按表回写处理
