/**
 * MVU Store — SSE 连接管理、工作日志缓存、胶囊数据派生
 */
import { nextTick } from 'vue'
import { defineStore } from 'pinia'
import type { MvuWorkLogEntry, StateVariables, StatusTableDef } from '../types/models'

export interface CapsuleItem {
  field: string
  value: string
  flashing: boolean
}

/** SSE catch-up 会连续推送多条 commit/error，尾部防抖合并为一次 GET /state */
const FETCH_STATE_DEBOUNCE_MS = 100

/** 多行同列名时，胶囊左侧标签：行标识与列名的分隔（与 MVU_AGENT「列=维度」并存） */
const CAPSULE_ROW_COL_SEP = ' · '

export const useMvuStore = defineStore('mvu', {
  state: () => ({
    isConnected: false,
    stateVariables: null as StateVariables | null,
    workLogs: [] as MvuWorkLogEntry[],
    isRunning: false,
    /**
     * 本次 SSE 连接建立后是否收到过 triggered；用于避免重放/竞态导致的「未跑 MVU 却触发收尾扫描」。
     */
    sawTriggeredSinceConnect: false,
    /**
     * disconnect 置位，connect 在 nextTick 清除；用于区分「断连把 isRunning 拉低」与「本轮 MVU 正常结束」。
     */
    tailScanSuppressed: false,
    _eventSource: null as EventSource | null,
    _reconnectDelay: 1000,
    _reconnectTimer: null as ReturnType<typeof setTimeout> | null,
    _activeChatId: null as string | null,
    _fetchStateTimer: null as ReturnType<typeof setTimeout> | null,
  }),

  getters: {
    /** 胶囊条是否允许在 isRunning 回落后播放「收尾扫描」一周期 */
    allowCapsuleScanTail(): boolean {
      return this.sawTriggeredSinceConnect && !this.tailScanSuppressed
    },

    capsuleData(): CapsuleItem[] {
      const tables: StatusTableDef[] = this.stateVariables?.tables ?? []
      if (tables.length === 0) return []
      const firstTable: StatusTableDef | undefined = tables[0]
      if (!firstTable) return []
      const cols: string[] = firstTable.columns ?? []
      if (cols.length === 0) return []
      const rows = firstTable.rows ?? []
      if (rows.length === 0) return []
      const multiRow = rows.length > 1
      const out: CapsuleItem[] = []
      for (const row of rows) {
        for (const col of cols) {
          const value = row.cells?.[col] ?? ''
          const field = multiRow ? `${row.field}${CAPSULE_ROW_COL_SEP}${col}` : col
          out.push({ field, value, flashing: false })
        }
      }
      return out
    },
  },

  actions: {
    _appendWorkLog(entry: MvuWorkLogEntry) {
      this.workLogs.push(entry)
      if (this.workLogs.length > 200) {
        this.workLogs = this.workLogs.slice(-200)
      }
    },

    connect(chatId: string) {
      if (this._eventSource) this.disconnect()
      this._activeChatId = chatId
      this.workLogs = []
      this.isRunning = false
      this.sawTriggeredSinceConnect = false

      const url = `/api/mvu/${chatId}/stream`
      const es = new EventSource(url)
      this._eventSource = es
      this.isConnected = true

      // 连接建立后立即拉取当前状态，确保预置 stateVariables 即时展示
      this.fetchState(chatId)

      es.addEventListener('log_history', (e: MessageEvent) => {
        try {
          const entry: MvuWorkLogEntry = JSON.parse(e.data)
          this._appendWorkLog(entry)
        } catch { /* ignore malformed */ }
      })

      es.addEventListener('log_entry', (e: MessageEvent) => {
        try {
          const entry: MvuWorkLogEntry = JSON.parse(e.data)
          this._appendWorkLog(entry)
          if (entry.eventType === 'triggered') {
            this.sawTriggeredSinceConnect = true
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

      void nextTick(() => {
        this.tailScanSuppressed = false
      })
    },

    disconnect() {
      this.tailScanSuppressed = true
      this.sawTriggeredSinceConnect = false
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
