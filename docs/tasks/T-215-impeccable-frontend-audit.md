# T-215 Impeccable 前端设计审计

- status: completed（批次 I–VII）
- area: frontend
- theme: 语义 token / a11y / 动效属性级 transition / 弹层抽查

## 批次进度

| 批次 | 主题 | 状态 | 改动摘要 |
|------|------|------|----------|
| I | 语义 destructive | ✅ | `InitialStateEditor`、`SettingsDrawerGlobalAppearanceSection` WebGPU 删除钮 |
| II | 语义 status | ✅ | `MessageList` system、`WebSearchQuotaSummary`、`SettingsDrawerGlobalTtsSection` 进度条、`AssistantPanel` 空状态 icon |
| III | 弹层 a11y | ✅ | `AvatarCropper` → `useDialogBehavior` + `dialogAria` |
| IV | 动效收束 | ✅ | `AssistantPanel`/`MvuPanel`/`ChatSidebar` 去 `transition-all`；`ChatPage` 搜索区挂 `--motion-duration-expand` |
| V | 弹层族抽查 | ✅ | KG/GroupCreator a11y 已齐；`GroupCreator`/`CharacterEditor`/`MemberSettings` 属性级 transition |
| VI | warning token | ✅ | `AssistantPanel`「破坏」徽章、`CharacterEditorModal` 破坏性工具 → `--color-warning-*` |
| VII | detect 复扫 | ✅ | 审计域 88 findings，**全部**为 `design-system-font-size`（`text-[10px]`） |
| VIII | 残留 transition-all | ✅ | ChatSidebar/ChatInput/ModernSelect/ReasoningBubble/AvatarCropper/WorldBook/ModernAvatar |

## Detect 结论（批次 VII）

```text
npx impeccable detect --json \
  frontend/src/components/modals \
  frontend/src/components/chat \
  frontend/src/components/settings-drawer \
  frontend/src/components/AvatarCropper.vue \
  frontend/src/components/WebSearchQuotaSummary.vue
→ 88 × design-system-font-size (text-[10px] off DESIGN.md ramp)
```

**处理决策**：不在本轮批量改 10px chip/badge。产品为 dense cockpit，`text-[10px]` 用于 SYSTEM/工具徽章等；若要消 advisory，应先在 `DESIGN.md` 增加 `caption-xs: 0.625rem` 再迁移，属后续设计系统扩展。

## 已知保留

| 项 | 说明 |
|----|------|
| 顶栏 morph / FLIP / Agent·TTS chip | 420/520/380ms 编排动画 |
| `StateVariablesBar` gradient | DESIGN 唯一允许背景渐变 |
| ChatPage 搜索 `--chat-search-*-ms` | 与搜索状态机绑定 |
| `CodeViewer` amber/emerald/sky | 语法高亮，非 UI status |
| 残留 `transition-all` | ✅ 批次 VIII 已收束（仅保留 utilities.css 工具类定义） |
| `text-[10px]` ×88 | 见上；待 DESIGN caption 阶 |

## 批次 VIII（残留 transition-all）

| 文件 | 处理 |
|------|------|
| `ChatSidebar` | 去掉冗余 `transition-all`（已有 `interactive-surface`） |
| `ChatInput` 操作钮 | `transition-[transform,box-shadow]` |
| `ModernSelect` | `transition-[background-color,border-color,box-shadow]` |
| `ReasoningBubble` 折叠钮 | 位置/尺寸/旋转属性级 |
| `AvatarCropper` 上传区 | `transition-[background-color,border-color]` |
| `SettingsDrawerChatWorldBookSection` | `transition-[border-color,opacity,background-color]` |
| `ModernAvatar` | `transition-[box-shadow,border-color]` |

## verify

```powershell
cd frontend
npm run test
npm run build
```

- 前端 113 tests + build 通过
