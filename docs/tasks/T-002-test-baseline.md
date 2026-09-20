# T-002 测试基线

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。


- status: done
- area: test
- priority: P0

## read_first

- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/src/utils/contentRegex.ts`
- `backend/requirements.txt`
- `backend/app/regex_compat.py`
- `backend/app/content_regex.py`
- `backend/app/content_regex_queue.py`
- `backend/app/llm/openai_compat.py`

## acceptance

- 新增后端 pytest 入口和最小测试文件。
- 后端测试覆盖 regex 字面量解析、正文正则替换语义、队列行为、LLM preset resolver 和 OpenAI 兼容 URL。
- 新增前端 `contentRegex.test.ts`，覆盖与后端一致的 golden case。
- `docs/RELEASE-v0.500.md` 中的验证命令与实际命令一致。

## verify

```powershell
cd E:\SimpleTavern\frontend
npm run test

cd E:\SimpleTavern\backend
python -m pytest tests/ -q
```

## next_hint

完成后读取 `docs/tasks/T-003-frontend-p0.md`。
