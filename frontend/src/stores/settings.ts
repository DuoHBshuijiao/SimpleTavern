import { defineStore } from 'pinia'

import type { Settings } from '../types/models'
import { apiGet, apiPut } from '../api/http'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: null as Settings | null,
    loading: false,
    error: null as string | null,
  }),
  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        this.settings = await apiGet<Settings>('/api/settings')
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
    async save(next: Settings) {
      this.loading = true
      this.error = null
      try {
        this.settings = await apiPut<Settings>('/api/settings', next)
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
  },
})


