/**
 * 全局通知队列（居中偏上、主题玻璃面板，z-index: --z-notification）。
 * 流式错误仍用 ChatPage 的 useErrorStack + ErrorModal。
 */
import { computed, ref } from 'vue'

export type NotifyConfirmVariant = 'danger' | 'default'

type NotifyAlertItem = {
  kind: 'alert'
  id: string
  title?: string
  message: string
  resolve: () => void
}

type NotifyConfirmItem = {
  kind: 'confirm'
  id: string
  title?: string
  message: string
  variant: NotifyConfirmVariant
  resolve: (value: boolean) => void
}

export type NotifyItem = NotifyAlertItem | NotifyConfirmItem

const queue = ref<NotifyItem[]>([])

const current = computed(() => queue.value[0] ?? null)

function nextId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/** 替代 window.alert；单按钮关闭，返回 Promise（关闭后 resolve）。 */
export function notifyMessage(message: string, options?: { title?: string }): Promise<void> {
  return new Promise((resolve) => {
    queue.value = [
      ...queue.value,
      {
        kind: 'alert',
        id: nextId(),
        title: options?.title,
        message,
        resolve,
      },
    ]
  })
}

/** 替代 window.confirm；返回 Promise<boolean>。 */
export function notifyConfirm(options: {
  title?: string
  message: string
  variant?: NotifyConfirmVariant
}): Promise<boolean> {
  return new Promise((resolve) => {
    queue.value = [
      ...queue.value,
      {
        kind: 'confirm',
        id: nextId(),
        title: options.title,
        message: options.message,
        variant: options.variant ?? 'default',
        resolve,
      },
    ]
  })
}

export function useNotify() {
  return {
    message: notifyMessage,
    confirm: notifyConfirm,
  }
}

/** 仅供 AppNotificationHost 使用 */
export function useNotifyHost() {
  return {
    queue,
    current,
    dismissAlert() {
      const first = queue.value[0]
      if (!first || first.kind !== 'alert') return
      queue.value = queue.value.slice(1)
      first.resolve()
    },
    confirmYes() {
      const first = queue.value[0]
      if (!first || first.kind !== 'confirm') return
      queue.value = queue.value.slice(1)
      first.resolve(true)
    },
    confirmNo() {
      const first = queue.value[0]
      if (!first || first.kind !== 'confirm') return
      queue.value = queue.value.slice(1)
      first.resolve(false)
    },
  }
}
