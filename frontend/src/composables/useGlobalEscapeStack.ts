/** 按 LIFO 顺序尝试关闭叠层；返回 true 表示已消费 Esc（含 notify host 拦截） */
export type CloseTopOverlayFn = () => boolean

export interface UseGlobalEscapeStackOptions {
  closeTopOverlay: CloseTopOverlayFn
  /** 无叠层可关时的次级行为（如关闭顶栏菜单、搜索栏） */
  onEscapeFallback: () => void
}

/**
 * 全局 Esc 键：优先关闭顶层叠层，否则执行 fallback。
 * closeTopOverlay 由页面注入具体 overlay 列表（见 createCloseTopOverlayHandler）。
 */
export function useGlobalEscapeStack(options: UseGlobalEscapeStackOptions) {
  function handleGlobalKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      if (options.closeTopOverlay()) {
        e.preventDefault()
        return
      }
      options.onEscapeFallback()
    }
  }

  return { handleGlobalKeydown }
}

export interface CloseTopOverlayHandlerOptions {
  hasActiveNotifyHost: () => boolean
  tryCloseErrorStack: () => boolean
  /** 按优先级排列的关闭尝试；首个返回 true 者胜出 */
  overlayClosers: Array<() => boolean>
}

export function createCloseTopOverlayHandler(options: CloseTopOverlayHandlerOptions): CloseTopOverlayFn {
  const { hasActiveNotifyHost, tryCloseErrorStack, overlayClosers } = options
  return () => {
    if (hasActiveNotifyHost()) return true
    if (tryCloseErrorStack()) return true
    for (const tryClose of overlayClosers) {
      if (tryClose()) return true
    }
    return false
  }
}
