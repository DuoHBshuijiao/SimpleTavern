import { defineStore } from 'pinia'

import type { CharacterCard } from '../types/models'
import { apiDelete, apiGet, apiPost, apiPut } from '../api/http'

export const useCharactersStore = defineStore('characters', {
  state: () => ({
    list: [] as CharacterCard[],
    loading: false,
    error: null as string | null,
  }),
  actions: {
    async loadAll() {
      this.loading = true
      this.error = null
      try {
        this.list = await apiGet<CharacterCard[]>('/api/characters')
      } catch (e: any) {
        this.error = e?.message ?? String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
    async create(card: CharacterCard) {
      const created = await apiPost<CharacterCard>('/api/characters', card)
      await this.loadAll()
      return created
    },
    async update(id: string, card: CharacterCard) {
      const updated = await apiPut<CharacterCard>(`/api/characters/${id}`, card)
      await this.loadAll()
      return updated
    },
    async remove(id: string) {
      await apiDelete(`/api/characters/${id}`)
      await this.loadAll()
    },
    async get(id: string) {
      return await apiGet<CharacterCard>(`/api/characters/${id}`)
    },
  },
})


