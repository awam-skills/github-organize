---
name: github-organize
description: >-
  审计并整理个人 GitHub 仓库与星标：找出无新提交的 fork、建议归档的自有仓、
  可取消/归类的星标，并导出含「仓库」「星标项目」工作表的 Excel。在用户提到
  GitHub 整理、清理 fork、整理星标、归档仓库、导出 GitHub Excel、github-organize
  时使用。
---

# GitHub 整理（仓库 + 星标）

基于 `gh` CLI 审计当前登录账号的 **Fork / 自有仓库 / 星标**，给出处理分类与建议，并可导出 Excel。

## 前置条件

```bash
gh auth status
```

- 需要已登录；删除仓库还需 `delete_repo` scope：
  `gh auth refresh -h github.com -s delete_repo`（用户需在浏览器完成授权）
- Excel 导出依赖 Python 包 `openpyxl`（脚本会尝试自动安装）

## 进度清单

```
GitHub 整理进度:
- [ ] 1. 确认 gh 登录账号
- [ ] 2. 审计 Fork（ahead / 本人提交）
- [ ] 3. 审计自有仓库（活跃度 / 归档建议）
- [ ] 4. 审计星标（归档上游 / 过期 / Lists 建议）
- [ ] 5. 向用户汇报摘要与可选操作
- [ ] 6. （可选）导出 Excel
- [ ] 7. （可选）执行删除 fork / 星标上游 / 归档——仅在用户明确确认后
```

## 工作流

### 1. 确认身份

```bash
gh api user --jq "{login, public_repos}"
```

后续所有操作针对该登录用户。

### 2. 审计 Fork（核心）

对每个 `isFork: true` 的仓库：

1. 取 `parent` 与默认分支（GraphQL 或 `gh api repos/{owner}/{repo}`）
2. 比较 `parentOwner:parentBranch...forkOwner:forkBranch`（URL 编码 `:` 为 `%3A`）
3. 查默认分支是否有本人提交：`gh api repos/{owner}/{repo}/commits?author={login}&per_page=1`

**无新提交判定（建议删除候选）：**

- `ahead_by == 0` 且本人提交数为 0；或
- 比对失败（404 / 无共同祖先）且本人提交数为 0

详细分类见 [reference.md](reference.md)。

### 3. 审计自有仓库

```bash
gh repo list {login} --limit 500 --json name,isFork,isPrivate,isArchived,primaryLanguage,pushedAt,stargazerCount,description,url
```

按最后推送时间：

| 距今 | 分类倾向 |
|------|----------|
| ≤180 天 | 活跃维护 |
| 180–365 天 | 半活跃 |
| >365 天且未归档 | 建议归档 |
| 已归档 | 已归档 |

无 description 的活跃仓：建议补描述 / topics。

### 4. 审计星标

用 GraphQL `viewer.starredRepositories` 分页拉取（含 `starredAt`、language、topics、`isArchived`、`pushedAt`）。

| 条件 | 分类倾向 |
|------|----------|
| 上游 `isArchived` | 建议取消星标 |
| 推送 >3 年 | 建议评估取消 |
| 推送 2–3 年 | 可保留，标「已过时」 |
| 近 90 天星标或上游仍活跃 | 保留并归入 Lists |

Lists 建议标签：`AI/LLM`、`量化/股票`、`前端`、`Node/后端`、`工具/DevOps`、`Android/自动化`、`机器学习`、`待读/未分类`。

### 5. 汇报与确认

先给**摘要数字**与**可执行下一步**（删 fork / 归档 / 导出 Excel / 建 Lists），**不要**在未确认时删除或归档。

删除 fork 时推荐顺序：

1. 对上游 `PUT user/starred/{owner}/{repo}`（已星标则跳过）
2. `gh repo delete {login}/{name} --yes`（需 `delete_repo`）
3. 汇总成功 / 失败

### 6. 导出 Excel

默认输出到用户桌面。执行：

```bash
python scripts/export_report.py
# 可选
python scripts/export_report.py --out "D:/path/GitHub整理建议.xlsx"
python scripts/export_report.py --keep fork1,fork2
```

生成工作簿：

1. **汇总说明** — 分类统计与使用说明  
2. **仓库** — 自有 + Fork，含处理分类与建议  
3. **星标项目** — 全部星标，含 Lists 建议与建议操作  

脚本路径相对本技能目录：[`scripts/export_report.py`](scripts/export_report.py)。

## 安全规则

- **删除 / 归档 / 批量 unstar**：必须用户明确点名或确认列表后再执行
- 用户说「除了 X 其他都删」时，严格按排除项保留
- 不要修改 `gh` 的 git config；不要 force 操作无关仓库
- 403 缺 `delete_repo` 时引导 `gh auth refresh`，等待用户完成浏览器授权后再重试

## 与其它技能关系

- 通用 `gh` issue/PR/CI：可用已有 `github` 技能
- 本技能专注：**个人仓库卫生 + 星标整理 + Excel 报告**
