# v0.500 发布清单

## 发布定位

`v0.500` 是稳定化质量版本，重点是修复错误、统一行为、补测试和修正文档。

## 发布前验证命令

```powershell
cd E:\SimpleTavern\frontend
npm run test
npm run build

cd E:\SimpleTavern\backend
python -m pytest tests/ -q
```

可选 smoke：

```powershell
cd E:\SimpleTavern
python deploy.py
```

启动后可检查：

```powershell
curl http://127.0.0.1:9091/api/health
curl http://127.0.0.1:9091/api/update/version
curl http://127.0.0.1:9091/api/data-integrity/issues
```

## 本地验证结果

- `cd frontend && npm run test`：通过，9 个测试文件 / 49 条用例。
- `cd frontend && npm run build`：通过，Vite 输出 chunk size warning，非失败。
- `cd backend && python -m pytest tests/ -q`：通过，104 条用例。

## Release body 草稿

### 修复

- 修复 LLM API 预设解析不一致，避免显式预设失效时静默回退或误用 TTS 预设。
- 修复正文正则显示语义和前后端兼容性问题。
- 修复 MVU 队列唤醒、启动清队列和 scanner 异常不可见问题。
- 修复设置抽屉未保存更改可能丢失、叠层遮挡和键盘关闭体验。
- 修复单聊创建时无效角色 ID 仍产生脏会话的问题。

### 改进

- 新增后端 pytest 基线和前端正文正则测试。
- 为长会话 markdown 渲染缓存增加上限。
- README 改为 v1.0 稳定化维护状态，补齐当前能力说明。
- 新增 AI 可接力的任务文档结构。

### 升级注意

- 本版本不新增大型功能模块。
- 若生成请求配置了不存在或不适合 LLM 的预设，后端会明确报错，不再静默回退。
