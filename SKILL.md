---
name: github-organize
description: "审计并整理个人 GitHub 仓库与星标：无新提交 fork、建议归档自有仓、可取消/归类星标；可选 Actions/Secrets 审计（默认关）；导出含人工处理列的 Excel，并可按表自动执行或 AI 归类回写。检测优先 scripts/audit.py。在用户提到 GitHub 整理、清理 fork、整理星标、归档仓库、workflow/secrets 审计、导出 GitHub Excel、按 Excel 处理、github-organize 时使用。通用 issue/PR/CI 用 github 技能。"
---

# GitHub 整理（仓库 + 星标 + 可选工作流/密钥）

**检测与分类一律用本技能脚本实现**；Agent 负责解读结果、向用户确认、再调用 `apply.py` 或 `process_excel.py` 执行。

## 运行约定

- 环境：本机已安装 `gh`（已验证 2.40.x+）与 Python 3.10+；Excel 需 `openpyxl`（导出/处理脚本会尝试自动安装）
- 前置：`gh auth status`；删除仓库需 `delete_repo` scope；读 Secrets 需仓 admin
- 允许效果：只读审计默认可跑；删除 / 归档 / 批量 unstar / 改 GitHub 状态必须先 `--dry-run`，用户确认后再 `--yes`
- 主可观测量：审计 JSON 的 `summary`，以及 Excel「处理结果 / 进一步建议」回写

`SKILL_DIR` = 本技能根目录（例如 `$HOME/.agents/skills/github/github-organize`）。

## 脚本与意图对照

| 用户意图 | 命令 | 效果 | 验证 |
|----------|------|------|------|
| 审计仓/星标 | `python "$SKILL_DIR/scripts/audit.py"` | 写审计 JSON | 看 `summary`；破坏性无 |
| 含 hygiene | 同上加 `--with-hygiene` | 另审计 Actions/Secrets | `summary.hygiene_skipped` 为 false |
| 导出 Excel | `python "$SKILL_DIR/scripts/export_report.py"` | 生成 xlsx | 打开表头含「人工处理」 |
| 按表执行 | `process_excel.py --from … --dry-run` → `--yes` | 回写处理结果 | 先 dry-run 摘要 |
| 按 JSON 批量 | `apply.py --from … --dry-run` → `--yes` | 删 fork/归档/unstar 等 | 与 Excel 流程二选一 |

参数速查：`--keep` / `--out` / `--skip-stars` / `--skip-fork-enrich` / `--with-hygiene` / `--hygiene-include-archived`；`process_excel` / `apply` 的 `--dry-run` 与 `--yes`。

## 按需阅读

| 时机 | 阅读 | 用途 |
|------|------|------|
| 解释「处理分类」或改分类规则 | [`references/classification.md`](references/classification.md) | Fork/自有/星标/hygiene 规则与推荐顺序 |
| 导出或按 Excel「人工处理」执行 | [`references/excel.md`](references/excel.md) | 列约定、可自动映射、缺列跳过 |
| 删仓失败、孤儿 Secret、路径疑惑 | [`references/gotchas.md`](references/gotchas.md) | 已验证坑与口径 |

## 启动时：先选分析范围（必须）

在跑 `audit.py` / `export_report.py` **之前**，向用户给出分析可选项并等待确认。

**优先用 `AskQuestion` 多选**（`allow_multiple: true`）。若工具支持选项默认勾选 / `selected`，则按下表预勾；不支持则在 prompt 中写明默认项，用户直接确认即按默认执行。

| 选项 id | 标签 | 默认勾选 | 脚本映射 |
|---------|------|----------|----------|
| `repos` | 仓库（Fork 清理 / 自有仓归档） | **是** | 始终包含（基础项） |
| `stars` | 星标整理 | **是** | 未选 → `--skip-stars` |
| `hygiene` | 工作流与密钥（Actions 失败 / 疑似孤儿 Secret） | **否** | 选中 → `--with-hygiene` |

提示文案示例：

> 本次 GitHub 整理要分析哪些内容？（可多选；默认已勾选「仓库」「星标」，工作流/密钥较慢且需 admin，默认不勾）

规则：

1. **用户已在消息里明确范围**（如「只整理星标」「审计 secrets」）→ 可跳过提问，直接按意图设 flag。
2. **至少保留一项**；若只勾了 hygiene、没勾仓库/星标，仍跑仓库基础拉取（hygiene 依赖自有仓列表），但可加 `--skip-stars`。
3. 脚本**默认不含** workflow/secret 检测；只有用户勾选 hygiene 或明确要求时才传 `--with-hygiene`。
4. 无 `AskQuestion` 时，用简短列表提问，并标明 `[✓] 仓库` `[✓] 星标` `[ ] 工作流与密钥`。

## 进度清单

```
GitHub 整理进度:
- [ ] 1. gh auth status
- [ ] 2. AskQuestion 确认分析范围（默认勾选：仓库 + 星标）
- [ ] 3. 运行 audit.py / export_report.py（仅在勾选时加 --with-hygiene）
- [ ] 4. 根据 summary 汇报（若启用 hygiene 则含 hygiene_attention）
- [ ] 5. （可选）export_report.py 导出 Excel
- [ ] 6. 提示用户：可在各表「人工处理」列逐行填写后，用 process_excel.py 回写处理
- [ ] 7. （可选）用户填完 Excel 后 process_excel.py --dry-run → --yes
- [ ] 8. （可选）对「需AI分析 / 不可自动」行：Agent 归类并给出进一步建议
- [ ] 9. （可选）用户确认后 apply.py --dry-run → --yes（按 JSON 批量，与 Excel 流程二选一即可）
```

## 强制规则：检测走代码

1. **禁止**用临时 shell/Node 重写 fork 比对、星标分页、workflow/secrets 审计、分类规则。
2. **必须**调用 `audit.py` 或 `export_report.py`。
3. 汇报优先用 `summary`：`forks_suggest_delete` / `own_suggest_archive` / `stars_suggest_unstar`；启用 hygiene 时还有 **`hygiene_attention`**。
4. 破坏性操作**只能**经 `apply.py` 或 `process_excel.py`，且先 `--dry-run`，确认后再 `--yes`。密钥删除默认不自动执行。

## 工作流

### 1. 审计

```bash
# 默认：仓库 + 星标（不含 workflow/secrets）
python "$SKILL_DIR/scripts/audit.py" --keep "fork1,fork2"

# 用户勾选了工作流与密钥时：
python "$SKILL_DIR/scripts/audit.py" --keep "fork1,fork2" --with-hygiene

# 仅仓库、跳过星标：
python "$SKILL_DIR/scripts/audit.py" --skip-stars
```

### 2. 汇报

关注 `forks_suggest_delete` / `own_suggest_archive` / `stars_suggest_unstar`。  
若 `summary.hygiene_skipped` 为 false，再汇报 `hygiene_attention` 与 `hygiene_by_cat`。

### 3. 导出 Excel

```bash
python "$SKILL_DIR/scripts/export_report.py" --keep "a,b" --audit-out audit.json
python "$SKILL_DIR/scripts/export_report.py" --with-hygiene --keep "a,b"
python "$SKILL_DIR/scripts/export_report.py" --from audit.json --out report.xlsx
```

标签页：**汇总说明** / **仓库** / **星标项目** / **工作流与密钥**（未启用 hygiene 时该表为空，汇总会注明未启用）

每张数据表含列：**人工处理**（默认「不处理」）、**处理结果**、**进一步建议**。列与映射细节见 [`references/excel.md`](references/excel.md)。

导出成功后，**必须提示用户**：

> 已导出 Excel。你可以在「仓库 / 星标项目 / 工作流与密钥」各表的「人工处理」列按行填写：
> - **按照建议**：采纳该行「处理分类 / 建议」中可自动执行的动作
> - **不处理**（默认）或**留空**：跳过
> - **其他处理方式**：直接写文字（如「删除」「删除并标星」「归档」「只星标上游不删」）
>
> 填完后把文件路径发我，可运行 `process_excel.py`：能自动的自动处理，不能自动的会归类并写入「进一步建议」，再由我解读给出下一步。

### 4. 按 Excel 处理（填完人工处理后）

```bash
python "$SKILL_DIR/scripts/process_excel.py" --from report.xlsx --dry-run
python "$SKILL_DIR/scripts/process_excel.py" --from report.xlsx --yes --out result.xlsx
```

- 先 `--dry-run`，把将执行项与「需 AI / 不可自动」项汇报给用户，确认后再 `--yes`
- 脚本回写 Excel：**处理结果**、**进一步建议**；stdout 输出 JSON 摘要（含 `needs_ai`、可选 `sheet_skipped`）
- Agent 对 `needs_ai` / 处理结果为「需AI分析」「不可自动」的行：根据人工处理文字与行内上下文**归类意图**，给出可执行的进一步建议（密钥/CI/Lists 等仍不擅自破坏性操作）
- 处理完成后把结果 Excel 路径与摘要返回用户

### 5. 按 audit JSON 执行（仅确认后，与步骤 4 二选一）

`apply.py --delete-forks --star-parents` 等。孤儿密钥请人工在 Settings 删除（除非用户另行明确要求自动化）。

## 安全规则

- 删除 / 归档 / 批量 unstar：必须用户明确确认
- 「除了 X 其他都删」→ `--exclude` / `--keep` 严格保留
- 不要改 git config
- Excel「人工处理」为「不处理」或**空** → 一律跳过
- 「删除」≠「删除并标星」：仅后者（或「按照建议」的删除类）会星标上游

## 完成标准

每次调用在适用范围内满足：已确认分析范围（或用户已明示）、检测经本包脚本完成、汇报引用 `summary`（及启用时的 hygiene 字段）、任何 GitHub 变更均经 dry-run 确认，且分支所需参考文件已按上表加载。

## 与其它技能

- 通用 issue/PR/CI：`github` 技能
- 本技能：仓卫生 + 星标 + 可选 workflow/secrets + Excel + 按表回写处理
