# T-006 最终验证与版本号

> **作废**：本文件中的 pytest / npm run test / Vitest 命令已取消。勿再运行或把测试加回仓库。黑盒规格见 docs/specs/BACKEND-API.md 与 docs/specs/FRONTEND-FEATURES.md。


- status: done
- area: release
- priority: P0

## read_first

- `docs/RELEASE-v0.500.md`
- `backend/app/version.py`
- `frontend/package.json`
- `backend/requirements.txt`

## acceptance

- 前端测试与构建通过。
- 后端 pytest 通过。
- `backend/app/version.py` 更新为 `APP_VERSION = "v0.500"`。
- `docs/state/LAST_HANDOFF.md` 指向 v0.500 完成后的下一步。
- 最终回复提供逐文件 `git add` 和中文 `git commit -m` 命令，供人工执行，不自动提交。

## verify

```powershell
cd E:\SimpleTavern\frontend
npm run test
npm run build

cd E:\SimpleTavern\backend
python -m pytest tests/ -q
```
