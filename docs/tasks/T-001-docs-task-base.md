# T-001 文档接力骨架

- status: done
- area: docs
- priority: P0

## read_first

- `CLAUDE.md`
- `README.md`
- `backend/app/main.py`
- `backend/app/version.py`

## acceptance

- `docs/00-INDEX.md` 能说明下一轮 AI 应如何接力。
- `docs/01-ROADMAP.md` 明确 `v0.500` 必做和推迟范围。
- `docs/02-BACKLOG.md` 列出首批任务顺序。
- `docs/state/CURRENT.md` 指向当前任务。
- `docs/state/LAST_HANDOFF.md` 只保留最短交接信息。
- `docs/RELEASE-v0.500.md` 包含验证命令和 Release body 草稿。

## verify

- 检查上述文件存在且内容不引用计划文件。
- 本任务不要求运行代码测试。

## next_hint

完成后读取 `docs/tasks/T-002-test-baseline.md`。
