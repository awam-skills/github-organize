---
name: github-organize
description: >-
  审计并整理个人 GitHub 仓库与星标：找出无新提交的 fork、建议归档的自有仓、
  可取消/归类的星标；并审计自有仓 Actions 失败与疑似孤儿 Secrets，导出含
  「仓库」「星标项目」「工作流与密钥」的 Excel。检测逻辑优先跑 scripts/audit.py。
  在用户提到 GitHub 整理、清理 fork、整理星标、归档仓库、workflow/secrets 审计、
  导出 GitHub Excel、github-organize 时使用。
---

# GitHub 整理（仓库 + 星标 + 工作流/密钥）

**检测与分类一律用本技能脚本实现**；Agent 负责解读结果、向用户确认、再调用 `apply.py` 执行。

## 脚本一览

路径相对本技能目录 `scripts/`：

| 脚本 | 作用 |
|------|------|
| [`common.py`](scripts/common.py) | 拉取 / 比对 / 分类 / **workflow·secrets 审计** |
| [`audit.py`](scripts/audit.py) | **检测入口**：输出审计 JSON + 摘要 |
| [`export_report.py`](scripts/export_report.py) | 检测或读 JSON → Excel |
| [`apply.py`](scripts/apply.py) | 确认后：星标上游、删 fork、归档、取消星标 |

分类细则见 [reference.md](reference.md)。

## 前置条件

```bash
gh auth status
```

- 删除仓库需要 `delete_repo`：`gh auth refresh -h github.com -s delete_repo`
- 读取仓库 Secrets 需要对该仓有 **admin**（否则密钥审计会标「权限不足」）
- Excel 需要 `openpyxl`（`export_report.py` 会尝试自动安装）

`SKILL_DIR` = 技能根目录，例如 `$HOME/.agents/skills/github-organize`

## 进度清单

```
GitHub 整理进度:
- [ ] 1. gh auth status
- [ ] 2. 运行 audit.py（含 hygiene，除非 --skip-hygiene）
- [ ] 3. 根据 summary 汇报（含 hygiene_attention）
- [ ] 4. （可选）export_report.py 导出 Excel
- [ ] 5. （可选）用户确认后 apply.py --dry-run → --yes
```

## 强制规则：检测走代码

1. **禁止**用临时 shell/Node 重写 fork 比对、星标分页、workflow/secrets 审计、分类规则。
2. **必须**调用 `audit.py` 或 `export_report.py`。
3. 汇报优先用 `summary`：`forks_suggest_delete` / `own_suggest_archive` / `stars_suggest_unstar` / **`hygiene_attention`**。
4. 破坏性操作**只能**经 `apply.py`，且先 `--dry-run`，确认后再 `--yes`。密钥删除默认不自动执行。

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

### 4. 执行（仅确认后）

`apply.py --delete-forks --star-parents` 等。孤儿密钥请人工在 Settings 删除（除非用户另行明确要求自动化）。

## 安全规则

- 删除 / 归档 / 批量 unstar：必须用户明确确认
- 「除了 X 其他都删」→ `--exclude` / `--keep` 严格保留
- 不要改 git config

## 与其它技能

- 通用 issue/PR/CI：`github` 技能
- 本技能：仓卫生 + 星标 + workflow/secrets + Excel
