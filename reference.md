# 分类规则参考

**实现位置**：`scripts/common.py` 中的 `classify_repo` / `classify_star` / `enrich_fork` / `run_audit`。  
Agent **不要**在对话里重新实现这些规则；改规则应改代码。

用户指定保留的仓库（`audit.py --keep`）优先于自动规则。

## Fork

| 条件 | 处理分类 | 建议要点 |
|------|----------|----------|
| 用户明确要求保留 | 保留-你指定保留 | 继续保留；可考虑只星标上游 |
| 近 180 天有活动且有本人提交 | 保留-近期在用 | 保留；重要改动可 PR 或独立成仓 |
| `ahead_by=0` 且无本人提交 | 建议删除-无新提交 | 删 fork；上游未星标则先打星 |
| 无本人提交但 `ahead_by>0` | 建议评估后删除 | 多为分支漂移；确认无独特改动后删 |
| 有本人提交且 >约 2 年未推送 | 建议评估-有提交但很久未用 | 确认补丁价值；无价值则删，有价值则 PR/迁仓 |
| 有本人提交且仍较新 | 保留-有本人提交 | 评估是否贡献上游 |
| 比对 404 / 无共同祖先，且无本人提交 | 建议删除-无新提交（比对失败） | 同上，删除前给上游打星 |

### 比对 API

```
GET /repos/{fork}/compare/{parentOwner}%3A{parentBranch}...{forkOwner}%3A{forkBranch}
```

优先使用与 fork 默认分支**同名**的上游分支；不存在则用上游默认分支。

### 本人提交

```
GET /repos/{owner}/{repo}/commits?author={login}&per_page=1
```

只覆盖默认分支历史；空数组 / 空仓库视为无本人提交。

## 自有仓库

| 条件 | 处理分类 |
|------|----------|
| `isArchived` | 已归档 |
| 最后推送 ≤180 天 | 活跃维护 |
| 180–365 天 | 半活跃 |
| >365 天且未归档 | 建议归档-长期未更新 |

活跃但无 description：建议补 description 与 topics；有 star 的旧仓优先 Archive 而非删除。

## 星标

| 条件 | 处理分类 |
|------|----------|
| 上游已 archived | 建议取消星标-上游已归档 |
| 最后推送 >3 年 | 建议评估取消-长期未更新 |
| 最后推送 2–3 年 | 可保留但标为过时 |
| 星标时间 ≤90 天 | 近期星标-保留并归类 |
| 上游一年内有更新 | 保留-上游仍活跃 |
| 其它 | 保留-一般参考 |

### Lists 映射（topics / 描述 / 语言启发式）

| List | 关键词示例 |
|------|------------|
| AI/LLM | llm, openai, chatgpt, ai, langchain, gpt, agent, rag |
| 量化/股票 | stock, quant, trading, finance |
| 前端 | vue, react, frontend, css, vite, webpack |
| Node/后端 | nodejs, nestjs, express, egg |
| 工具/DevOps | docker, devops, kubernetes, cli, shell |
| Android/自动化 | android, autojs, hamibot |
| 机器学习 | machine-learning, deep-learning, pytorch, tensorflow |
| 待读/未分类 | 未命中以上 |

## Excel 列约定

### 仓库

仓库名、完整名、类型、可见性、是否归档、主语言、Stars、描述、创建时间、最后推送、距今推送天数、上游仓库、ahead、behind、本人提交、处理分类、建议、URL

### 星标项目

仓库、Owner、主语言、Topics、描述、上游 Stars、是否归档、是否 Fork、最后推送、距今推送天数、星标时间、距今星标天数、处理分类、建议归入 List、建议、URL

### 工作流与密钥（自有仓）

仓库、是否归档、有 Workflow、Workflow 数、近期失败运行数、失败工作流名、Secrets 数、孤儿 Secrets 数、孤儿列表、CodeQL 状态、处理分类、建议、备注/错误、URL

实现：`scripts/common.py` → `audit_one_repo_hygiene` / `audit_hygiene`。

| 条件 | 处理分类 |
|------|----------|
| 近期 Actions 有 failure 运行 | 建议检查-工作流失败 |
| Secret 未在 `.github/workflows` 中以 `secrets.NAME` 出现 | 建议清理-疑似孤儿密钥 |
| 有 Secret 但无 workflow | 建议关注-有密钥无工作流 |
| 有 workflow 但读不到 secrets（无 admin） | 权限不足-跳过密钥 |
| CodeQL default setup 未配置 | 建议关注-CodeQL未配置 |
| 其它 | 正常 |

说明：失败运行来自 `actions/runs?status=failure` 最近一页，非严格日历 30 天；孤儿判定基于 workflow 文件文本，**动态名 / 可复用 workflow / 组织级密钥** 可能误报，删除前请人工确认。

## 推荐执行顺序（给用户的建议）

1. 删除「无新提交」类 fork（先星标上游）
2. 批量 Archive 超过 1–3 年未更新的自有仓
3. 处理「工作流与密钥」表中失败 CI / 孤儿 Secret
4. 为星标建 GitHub Lists，优先处理「建议取消」与「近期星标」
5. Profile 只 pin 少量活跃项目
