# Changelog

## v0.600

### 系统性升级

- 建立统一的 Surface/Card/Button/Input/Modal/Drawer/Popover 视觉语言，补齐焦点环、loading、danger、secondary、disabled、active 与 reduced-motion 状态。
- 收束主要页面和面板中的硬编码颜色、阴影、圆角、z-index 与多层 `backdrop-blur`，让聊天列表、消息气泡、输入区、侧栏、设置抽屉、助手/MVU/TTS 面板、知识图谱和 HTTP Log 的视觉层级更一致。
- 统一导入导出、群聊设置、消息编辑、WebGPU、世界书、知识图谱等弹窗外层 surface，并补充关键关闭按钮 `aria-label`、dialog 标题关联、Esc 与焦点恢复工具。
- 优化高频交互的微动效与性能表现，减少重面板模糊叠层，保留列表渲染、Markdown 缓存、KG/WebGPU/TTS 面板的轻量更新策略。

### 稳定性与测试

- MVU/知识图谱路由集中会话加载 fast-fail，缺失会话返回结构化 `code/message/chatId`，便于前端和用户定位问题。
- 新增前端 UI primitive、dialog focus 工具测试，保留正文正则显示测试；新增后端 MVU route 错误测试。

## v0.500

### 修复

- 统一 LLM API 预设解析，显式预设不存在、误选 TTS 预设或缺少凭证时会 fast fail，不再静默回退到其他端点。
- 修复 MVU worker 首次启动时清空正文正则队列导致提取结果丢失的问题，并在队列入队后唤醒 worker。
- 修复正文正则扫描器高频全库扫描、异常静默吞掉和首条 greeting 入队问题。
- 修复单聊创建时角色不存在仍创建脏会话的问题。
- 修复 ZIP 导入长期记忆失败时无 warning 的问题。
- 修复设置抽屉关闭会丢弃未保存更改、MVU 草稿被外部刷新覆盖、抽屉叠层被助手/MVU 面板遮挡的问题。
- 修复前端正文正则显示处理与后端替换语义不一致的问题。

### 改进

- 新增后端 pytest 基线，覆盖正文正则、regex 字面量、队列、API 预设解析和 OpenAI 兼容 URL。
- 新增前端正文正则 golden 测试。
- 为 MessageList markdown HTML 缓存增加 LRU 上限，降低长会话内存增长风险。
- 统一高风险确认框到应用内通知系统，并增强 Esc/焦点行为。
- README 改为 v1.0 稳定化维护状态，并补齐 MVU、正文正则、知识图谱、会话分叉和数据完整性说明。
- 新增 `docs/` 任务接力与 `docs/RELEASE-v0.500.md` 发布清单。
