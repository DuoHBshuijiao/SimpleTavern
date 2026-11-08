# 当前任务

- current: v1.000 发布验收（2026-11-08）。新功能已冻结，只修问题。
- checklist: `docs/tasks/T-814-v1000-release-acceptance.md`。作者的 18 项决定、问题记录和验收记录都在这里。
- status: 自动和沙箱核对项已完成，剩作者手测三晚（真实模型、真实账号、数据进出）、Vertex 真实项目验收和发布动作。运行版本仍为 v0.810，作者手测通过后直接改 v1.000。
- next_read: `docs/00-INDEX.md`（测试政策）、`docs/specs/BACKEND-API.md` 的「2026-11-07 增补」、`docs/specs/FRONTEND-FEATURES.md`
- goal: 作者手测发现问题就修，每次修改后重跑两套黑盒检查；不加新功能。

## 怎么验证

```bash
venv/Scripts/python tools/api-check/run.py
```

```bash
venv/Scripts/python tools/ui-check/run.py
```

- 两套都是黑盒检查，写检查的一方不看实现，每项都要有能失败的对照。
- `ui-check` 的 `built`、`core`、`modals` 等在构建产物上跑；模糊等效果只认构建产物。
- 真实 `data/` 只读，作者自己的实例在 9081/9091，不要关。

## 版本宣告

- v1.000（验收中）：T-832 三家协议、思考预算和错误处理修复、聊天界面和设置页打磨、两套黑盒检查。详见 `CHANGELOG.md`。
- 放到 1.0 之后：Codex 额度显示、出错重试按钮、备份可选是否含密钥、主题按钮对比度、世界书绑定两处记录合一、插件 SDK、跨设备同步、AWS 签名、局域网登录。
