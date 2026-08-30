# 已验证注意点

在排错、执行破坏性操作前，或用户质疑分类结果时阅读。

| 现象 | 原因 | 处理 |
|------|------|------|
| 删仓失败 / `HTTP 403` | `gh` 缺 `delete_repo` scope | `gh auth refresh -h github.com -s delete_repo` |
| 密钥审计「权限不足」 | 对该仓无 admin | 跳过或换有权限账号；勿臆造密钥列表 |
| 孤儿 Secret 误报 | 动态名、可复用 workflow、组织级密钥未出现在本仓 workflow 文本 | 删除前人工确认 Settings |
| 失败运行数偏少/偏多 | 取自 `actions/runs?status=failure` 最近一页，非严格 30 天窗口 | 汇报时说明口径 |
| 「删除」未星标上游 | 自由文字「删除」刻意不打星；「按照建议」删除类会打星 | 需要打星时写「删除并标星」 |
| hygiene 未出现在摘要 | 默认关闭 | 需 `--with-hygiene` 或勾选「工作流与密钥」 |
| Windows 路径 / `SKILL_DIR` | 技能实际在 `.../skills/github/github-organize` | 用本包绝对路径或相对本技能根目录调用脚本 |
| 只勾 hygiene | 仍需自有仓列表 | 仍跑仓库基础拉取；可用 `--skip-stars` |
