/**
 * FAB 碰撞检测与弹开
 *
 * 当两个浮动组件矩形相交时，将被拖动方沿水平方向推开，
 * 垂直中线对齐被重叠方。
 */

const MIN_GAP = 6  // 弹开后的最小视觉间隙 px

/**
 * 聊天 FAB 碰撞检测用间隙（略小，避免 DOM 取整/CSS 过渡与逻辑矩形不一致时漏判）
 */
export const FAB_COLLISION_GAP_PX = 4

/**
 * 检测两个矩形是否相交（含间隙 gap：两矩形边距小于 gap 即视为重叠）。
 */
export function rectsOverlap(a: DOMRect, b: DOMRect, gap: number = MIN_GAP): boolean {
  return !(
    a.right + gap <= b.left ||
    b.right + gap <= a.left ||
    a.bottom + gap <= b.top ||
    b.bottom + gap <= a.top
  )
}

/**
 * 计算弹开后的 moving 位置。
 *
 * @param moving  被拖动方矩形
 * @param other   未被拖动方矩形
 * @param preferSide  优先推向哪一侧
 * @returns 弹开后 moving 的新 { left, top }
 */
export function resolveOverlap(
  moving: DOMRect,
  other: DOMRect,
  preferSide: 'left' | 'right' = 'right',
): { left: number; top: number } {
  // 垂直对齐：moving 中线 = other 中线
  const otherCenterY = other.top + other.height / 2
  const newTop = otherCenterY - moving.height / 2

  // 水平推开：向 preferSide 推
  let newLeft: number
  if (preferSide === 'right') {
    newLeft = other.right + MIN_GAP
    // 如果推出屏幕右侧，改向左推
    if (newLeft + moving.width > window.innerWidth) {
      newLeft = other.left - moving.width - MIN_GAP
    }
  } else {
    newLeft = other.left - moving.width - MIN_GAP
    // 如果推出屏幕左侧，改向右推
    if (newLeft < 0) {
      newLeft = other.right + MIN_GAP
    }
  }

  return {
    left: Math.max(0, Math.min(newLeft, window.innerWidth - moving.width)),
    top: Math.max(0, Math.min(newTop, window.innerHeight - moving.height)),
  }
}

const EDGE_PAD = 8

function centerY(rect: DOMRect): number {
  return rect.top + rect.height / 2
}

function topFits(t: number, minTop: number, maxTop: number): boolean {
  return t >= minTop - 0.5 && t <= maxTop + 0.5
}

/**
 * fixed 保持不动，仅计算 moving 的新 top。
 * 用两者垂直中线判断：moving 中线在 fixed 中线之上则优先挪到 fixed 上方，否则优先挪到下方（相等情况视为偏下，优先下方）。
 */
export function computeVerticalNonOverlapTop(
  fixedRect: DOMRect,
  movingRect: DOMRect,
  minTop: number,
): number {
  if (!rectsOverlap(fixedRect, movingRect, FAB_COLLISION_GAP_PX)) return movingRect.top

  const h = movingRect.height
  const maxTop = window.innerHeight - h - EDGE_PAD

  const belowTop = fixedRect.bottom + MIN_GAP
  const aboveTop = fixedRect.top - h - MIN_GAP

  /** moving 中线相对 fixed 中线：偏上则先尝试放到 fixed 上侧，偏下则先尝试下侧 */
  const preferBelow = centerY(movingRect) >= centerY(fixedRect)

  const tryOrder = preferBelow
    ? [belowTop, aboveTop] as const
    : [aboveTop, belowTop] as const

  for (const cand of tryOrder) {
    if (topFits(cand, minTop, maxTop)) return cand
  }

  let cand = Math.max(minTop, belowTop)
  if (cand <= maxTop) return cand

  cand = Math.min(aboveTop, maxTop)
  if (cand >= minTop) return cand

  return Math.max(minTop, Math.min(movingRect.top, maxTop))
}

/** TTS 为 moving、助手为 fixed */
export function computeTtsNonOverlapTop(
  assistantRect: DOMRect,
  ttsRect: DOMRect,
  minTop: number,
): number {
  return computeVerticalNonOverlapTop(assistantRect, ttsRect, minTop)
}

/** 助手为 moving、TTS 为 fixed */
export function computeAssistantNonOverlapTop(
  ttsRect: DOMRect,
  assistantRect: DOMRect,
  minTop: number,
): number {
  return computeVerticalNonOverlapTop(ttsRect, assistantRect, minTop)
}
