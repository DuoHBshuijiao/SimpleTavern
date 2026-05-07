export interface FlexWrapMeasureItem {
  offsetTop: number
  offsetHeight: number
  offsetWidth: number
}

const VISUAL_LINE_TOP_TOLERANCE_PX = 2

export function computeFlexWrapExtraHeight(items: FlexWrapMeasureItem[]): number {
  const visibleItems = items.filter((item) => item.offsetWidth > 0 && item.offsetHeight > 0)
  if (visibleItems.length <= 1) return 0

  const sorted = [...visibleItems].sort((a, b) => a.offsetTop - b.offsetTop)
  const firstLineTop = sorted[0]!.offsetTop
  let firstLineBottom = firstLineTop
  let totalBottom = firstLineTop

  for (const item of sorted) {
    const itemBottom = item.offsetTop + item.offsetHeight
    totalBottom = Math.max(totalBottom, itemBottom)
    if (Math.abs(item.offsetTop - firstLineTop) <= VISUAL_LINE_TOP_TOLERANCE_PX) {
      firstLineBottom = Math.max(firstLineBottom, itemBottom)
    }
  }

  return Math.max(0, Math.ceil(totalBottom - firstLineBottom))
}
