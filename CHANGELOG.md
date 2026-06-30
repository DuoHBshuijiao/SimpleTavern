# Changelog

## v0.700

### 组件化与测试基座

- 引入前端组件测试基座：新增 `@vue/test-utils` + `happy-dom`，建立可挂载 SFC 的组件测试模式与 `ThemedCheckbox` 示例。
- 从 `ChatPage.vue`（约 7166 行）提炼 3 个低风险 composable，行为不变并各配单测：`useChatSearch`（会话内搜索状态机/动画时序/导航）、`useImageStickyBinding`（图片占位粘性绑定 + 生成失败回退对话框）、`useForkLineage`（分叉血缘加载/缓存/防抖/切会话清理）。

### 数据完整性与导入可观测性

- 数据完整性扫描从仅 chat/assistant JSON 扩展到 `settings.json`、`assistant_settings.json`、`characters/`、`worldbooks/`，并新增 chat.characterId 的 orphan 引用检测。新增类别一律“仅检测、不自动修复”（repairAction=none），孤儿会话所在文件不会被按 chat 规则自动删除。
- 启动巡检前端区分“可自动清理”与“需人工处理”两类，绝不自动改动设置/角色/世界书。
- 修复导入结果提示在存在顶层 warning 时丢失 MVU 兼容 warning 的互斥问题；TXT(Version 2) 会话导入透传此前被静默丢弃的逐行 warning。

### 测试

- 新增前端 `ThemedCheckbox`、`useChatSearch`、`useImageStickyBinding`、`useForkLineage`、`formatImportResultMessage` 测试；新增后端数据完整性扩展、导入 warning 透传测试。前端 83 测试、后端 114 测试全通过。

## v0.601

### 无障碍

- 新增设计规范约束：禁止在原生元素上使用裸 `title` 属性作为提示或可访问标签，统一改用 `aria-label`（或可见文本 / `aria-labelledby`），并写入 `DESIGN.md` 与 `PRODUCT.md`。
- 新增前端测试守卫 `frontend/src/utils/noBareTitleAttr.test.ts`：扫描全部 `.vue`，断言原生元素不出现 `title` / `:title` 属性（PascalCase 组件的 `title` prop 不受影响），防止该约束回归；当前代码 0 违规。

## v0.600

### 系统性升级

- 建立统一的 Surface/Card/Button/Input/Modal/Drawer/Popover 视觉语言，补齐焦点环、loading、danger、secondary、disabled、active 与 reduced-motion 状态。
- 收束主要页面和面板中的硬编码颜色、阴影、圆角、z-index 与多层 `backdrop-blur`，让聊天列表、消息气泡、输入区、侧栏、设置抽屉、助手/MVU/TTS 面板、知识图谱和 HTTP Log 的视觉层级更一致。
- 统一导入导出、群聊设置、消息编辑、WebGPU、世界书、知识图谱等弹窗外层 surface，并补充关键关闭按钮 `aria-label`、dialog 标题关联、Esc 与焦点恢复工具；全量弹层接入 `useDialogBehavior` / `dialogAria`。
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
