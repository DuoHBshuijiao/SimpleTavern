# T-004 后端 P0 修复

- status: done
- area: backend
- priority: P0

## read_first

- `backend/app/routes/generate.py`
- `backend/app/routes/assistant.py`
- `backend/app/services/mvu_daemon.py`
- `backend/app/content_regex_scanner.py`
- `backend/app/content_regex_queue.py`
- `backend/app/routes/chats.py`
- `backend/app/routes/import_export.py`
- `backend/app/schemas.py`

## acceptance

- LLM preset 解析集中且一致，显式预设错误会 fast fail。
- TTS preset 不会被当作 LLM preset 使用。
- generate、assistant、MVU 在同一模型和预设配置下解析到一致凭证。
- 正文正则 scanner 使用扫描深度并记录异常。
- MVU 队列不会在 worker 首次启动时无条件清空，队列阈值会触发唤醒。
- 无效角色 ID 创建单聊返回明确 404。
- import/export 恢复长期记忆失败会产生 warning 或日志。

## verify

```powershell
cd E:\SimpleTavern\backend
python -m pytest tests/ -q
```

## next_hint

完成后读取 `docs/tasks/T-005-release-docs.md`。
