/**
 * MVU Store — SSE 连接管理、工作日志缓存、胶囊数据派生
 */
import { defineStore } from 'pinia'
import type { MvuWorkLogEntry, StateVariables, StatusTableDef, StatusTableRow } from '../types/models'

export interface CapsuleItem {
  field: string
  value: string
  flashing: boolean
}

/** SSE catch-up 会连续推送多条 commit/error，尾部防抖合并为一次 GET /state */
const FETCH_STATE_DEBOUNCE_MS = 100

export const useMvuStore = defineStore('mvu', {
  state: () => ({
    isConnected: false,
    stateVariables: null as StateVariables | null,
    workLogs: [] as MvuWorkLogEntry[],
    isRunning: false,
    _eventSource: null as EventSource | null,
    _reconnectDelay: 1000,
    _reconnectTimer: null as ReturnType<typeof setTimeout> | null,
    _activeChatId: null as string | null,
    _fetchStateTimer: null as ReturnType<typeof setTimeout> | null,
  }),

  getters: {
    capsuleData(): CapsuleItem[] {
      const tables: StatusTableDef[] = this.stateVariables?.tables ?? []
      if (tables.length === 0) return []
      const firstTable: StatusTableDef | undefined = tables[0]
      if (!firstTable) return []
      const cols: string[] = firstTable.columns ?? []
      if (cols.length === 0) return []
      const firstCol: string | undefined = cols[0]
      if (!firstCol) return []
      return firstTable.rows.map((row: StatusTableRow) => ({
        field: row.field,
        value: row.cells?.[firstCol] ?? '',
        flashing: false,
      }))
    },
  },

  actions: {
    connect(chatId: string) {
      if (this._eventSource) this.disconnect()
      this._activeChatId = chatId
      this.workLogs = []
      this.isRunning = false

      const url = `/api/mvu/${chatId}/stream`
      const es = new EventSource(url)
      this._eventSource = es
      this.isConnected = true

      // 连接建立后立即拉取当前状态，确保预置 stateVariables 即时展示
      this.fetchState(chatId)

      es.addEventListener('log_entry', (e: MessageEvent) => {
        try {
          const entry: MvuWorkLogEntry = JSON.parse(e.data)
          this.workLogs.push(entry)
          if (this.workLogs.length > 200) {
            this.workLogs = this.workLogs.slice(-200)
          }
          if (entry.eventType === 'triggered') {
            this.isRunning = true
          } else if (entry.eventType === 'commit' || entry.eventType === 'error') {
            this.isRunning = false
            this._scheduleFetchState(chatId)
          }
        } catch { /* ignore malformed */ }
      })

      es.addEventListener('done', () => {
        this.isRunning = false
        this._scheduleFetchState(chatId)
      })

      es.addEventListener('error', () => {
        this.isRunning = false
      })

      es.addEventListener('heartbeat', () => { /* no-op */ })

      es.onerror = () => {
        this.isConnected = false
        es.close()
        this._scheduleReconnect(chatId)
      }
    },

    disconnect() {
      if (this._fetchStateTimer) {
        clearTimeout(this._fetchStateTimer)
        this._fetchStateTimer = null
      }
      if (this._reconnectTimer) {
        clearTimeout(this._reconnectTimer)
        this._reconnectTimer = null
      }
      if (this._eventSource) {
        this._eventSource.close()
        this._eventSource = null
      }
      this.isConnected = false
      this.isRunning = false
    },

    async fetchState(chatId: string) {
      try {
        const resp = await fetch(`/api/mvu/${chatId}/state`)
        if (!resp.ok) return
        const data = await resp.json()
        if (data.ok && data.stateVariables) {
          this.stateVariables = data.stateVariables
        }
      } catch { /* ignore network errors */ }
    },

    _scheduleFetchState(chatId: string) {
      if (this._fetchStateTimer) clearTimeout(this._fetchStateTimer)
      this._fetchStateTimer = setTimeout(() => {
        this._fetchStateTimer = null
        if (this._activeChatId !== chatId) return
        void this.fetchState(chatId)
      }, FETCH_STATE_DEBOUNCE_MS)
    },

    _scheduleReconnect(chatId: string) {
      if (this._reconnectTimer) clearTimeout(this._reconnectTimer)
      const delay = Math.min(this._reconnectDelay, 30000)
      this._reconnectTimer = setTimeout(() => {
        this._reconnectDelay = Math.min(this._reconnectDelay * 2, 30000)
        this.connect(chatId)
      }, delay)
    },
  },
})
