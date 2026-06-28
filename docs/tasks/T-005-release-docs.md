# T-005 发布文档

- status: done
- area: docs
- priority: P1

## read_first

- `README.md`
- `CHANGELOG.md`
- `docs/01-ROADMAP.md`
- `docs/RELEASE-v0.500.md`
- `backend/app/main.py`
- `backend/app/routes/update.py`

## acceptance

- README 首行不再声明停更，改为 v1.0 稳定化维护状态。
- README 补齐 MVU、正文正则、知识图谱、会话 fork、数据完整性等当前能力说明。
- 新建或更新 `CHANGELOG.md`，包含 `v0.410 -> v0.500` 的修复摘要。
- `docs/RELEASE-v0.500.md` 与实际验证结果一致。

## verify

- README 链接和 API 表不引用不存在的路由。
- `CHANGELOG.md` 有 `v0.500` 条目。

## next_hint

完成后读取 `docs/tasks/T-006-final-verify.md`。
