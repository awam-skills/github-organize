---
name: github-organize
description: >-
  审计并整理个人 GitHub 仓库与星标：找出无新提交的 fork、建议归档的自有仓、
  可取消/归类的星标，并导出含「仓库」「星标项目」工作表的 Excel。检测逻辑优先跑
  scripts/audit.py（勿手写重复 gh 流程）。在用户提到 GitHub 整理、清理 fork、
  整理星标、归档仓库、导出 GitHub Excel、github-organize 时使用。
---

# GitHub 整理（仓库 + 星标）

**检测与分类一律用本技能脚本实现**；Agent 负责解读结果、向用户确认、再调用 `apply.py` 执行。

## 脚本一览

路径相对本技能目录 `scripts/`：

| 脚本 | 作用 |
|------|------|
| [`common.py`](scripts/common.py) | 拉取 / 比对 / 分类（被其它脚本 import） |
| [`audit.py`](scripts/audit.py) | **检测入口**：输出审计 JSON + 摘要 |
| [`export_report.py`](scripts/export_report.py) | 检测或读 JSON → Excel（汇总说明 / 仓库 / 星标项目） |
| [`apply.py`](scripts/apply.py) | 确认后：星标上游、删 fork、归档自有仓、取消星标 |

分类细则见 [reference.md](reference.md)。

## 前置条件

```bash
gh auth status
```

- 删除仓库需要 `delete_repo`：`gh auth refresh -h github.com -s delete_repo`
- Excel 需要 `openpyxl`（`export_report.py` 会尝试自动安装）

将 `SKILL_DIR` 设为技能根目录（含 `scripts/` 的那一层），例如：

`$HOME/.agents/skills/github-organize`

## 进度清单

```
GitHub 整理进度:
- [ ] 1. gh auth status
- [ ] 2. 运行 audit.py（或 export_report.py 顺带审计）
- [ ] 3. 根据 summary 向用户汇报
- [ ] 4. （可选）export_report.py 导出 Excel
- [ ] 5. （可选）用户确认后 apply.py --dry-run → --yes
```

## 强制规则：检测走代码

1. **禁止**用临时 shell/Node 重写 fork 比对、星标分页、分类规则。
2. **必须**调用 `audit.py` 或 `export_report.py`（二者内部共用 `common.run_audit`）。
3. 向用户展示时，优先引用 JSON 里的 `summary.forks_suggest_delete` / `own_suggest_archive` / `stars_suggest_unstar`。
4. 破坏性操作**只能**经 `apply.py`，且先 `--dry-run`，用户确认后再 `--yes`。

## 工作流

### 1. 审计（检测）

```bash
python "$SKILL_DIR/scripts/audit.py" --keep "fork1,fork2"
# 默认把完整 JSON 写到桌面 GitHub审计_*.json，stdout 打印摘要
```

常用参数：

- `--keep a,b` — 标记为「保留-你指定保留」
- `--out path.json` — 指定审计 JSON 路径
- `--skip-stars` — 只审计仓库（更快）
- `--skip-fork-enrich` — 跳过 fork 比对（不准确，仅调试）

### 2. 汇报

读取 stdout / JSON 的 `summary`：

- `forks_suggest_delete` — 建议删的 fork（含 parent）
- `own_suggest_archive` — 建议归档的自有仓
- `stars_suggest_unstar` — 建议取消星标
- `repo_by_cat` / `star_by_cat` — 分类计数

### 3. 导出 Excel（可选）

```bash
# 现场审计并导出
python "$SKILL_DIR/scripts/export_report.py" --keep "a,b" --audit-out audit.json

# 或基于已有审计 JSON
python "$SKILL_DIR/scripts/export_report.py" --from audit.json --out report.xlsx
```

### 4. 执行（仅用户确认后）

```bash
# 预览
python "$SKILL_DIR/scripts/apply.py" --from audit.json --delete-forks --star-parents --dry-run

# 执行：先星标上游再删「建议删除-无新提交」类 fork
python "$SKILL_DIR/scripts/apply.py" --from audit.json --delete-forks --star-parents --yes \
  --categories "建议删除-无新提交" --exclude "kept1,kept2"

# 归档自有仓 / 取消星标 同理
python "$SKILL_DIR/scripts/apply.py" --from audit.json --archive-own --dry-run
python "$SKILL_DIR/scripts/apply.py" --from audit.json --unstar --dry-run \
  --categories "建议取消星标-上游已归档"
```

缺 `delete_repo` 时 `apply.py` 会返回错误并提示 `gh auth refresh`；等用户完成浏览器授权后再重试。

## 安全规则

- 删除 / 归档 / 批量 unstar：必须用户明确确认列表
- 「除了 X 其他都删」→ `--exclude` 或 `--keep`（审计阶段）严格保留
- 不要改 git config；不要对无关仓库 force 操作

## 与其它技能

- 通用 issue/PR/CI：用 `github` 技能
- 本技能：个人仓卫生 + 星标整理 + Excel，**检测逻辑在 scripts/**
