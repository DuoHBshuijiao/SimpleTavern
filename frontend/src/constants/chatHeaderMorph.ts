/** 与 ChatPage 顶栏吸顶 morph 共用，供输入区等同步动画使用 */

export type HeaderMorphPhase = 'inset' | 'lifting' | 'full'

/** 阶段 1：顶栏上移贴顶（与输入区下沉同频） */
export const HEADER_LIFT_MS = 420
export const HEADER_LIFT_EASE = 'cubic-bezier(0.45, 0.05, 0.55, 0.95)'

/** 阶段 2：左右拉满与圆角 */
export const HEADER_SQUEEZE_MS = 520
export const HEADER_SQUEEZE_EASE = 'cubic-bezier(0.4, 0, 0.2, 1)'

/** 侧栏展开时顶栏回弹（与 ChatPage headerEasingMs 短暂 180 一致） */
export const HEADER_EXPAND_MS = 180

/** 与 ChatPage 主区 `duration-300`、侧栏 `transition-all duration-300` 一致，供输入壳 margin/transform 与布局同频 */
export const MAIN_LAYOUT_TRANSITION_MS = 300

/** TTS 顶栏「队列 + 播放」竖排近似高度（双 chip min-height 1.75rem + flex gap-2），与 TtsPlaybackFab 对齐 */
export const TTS_TOP_BAR_TWO_BTN_STACK_PX = 64

/** Agent 顶栏胶囊与 TTS 顶栏叠层之间的间距（与 Tailwind gap-2 一致） */
export const TOP_BAR_AGENT_AFTER_TTS_GAP_PX = 8
