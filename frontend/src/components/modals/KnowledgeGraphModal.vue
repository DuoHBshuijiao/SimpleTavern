<script setup lang="ts">
/**
 * 知识图谱可视化与手动维护（vis-network）。
 */
import { computed, nextTick, onUnmounted, ref, shallowRef, watch } from 'vue'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import 'vis-network/styles/vis-network.min.css'
import { X, RefreshCw, Plus, Trash2 } from 'lucide-vue-next'
import { apiPost, apiDelete } from '../../api/http'
import type { KgEntityType, KnowledgeGraphResponse } from '../../types/models'
import { useMvuStore } from '../../stores/mvu'
import {
  KG_ENTITY_TYPES,
  countActiveEntities,
  countRelations,
  knowledgeGraphToVisData,
} from '../../utils/kgVisNetwork'
import ModernSelect from '../ModernSelect.vue'

const props = defineProps<{
  show: boolean
  chatId: string | null
}>()

const emit = defineEmits<{
  'update:show': [boolean]
}>()

const mvuStore = useMvuStore()
const graphContainer = ref<HTMLElement | null>(null)
const network = shallowRef<Network | null>(null)
const loading = ref(false)
const saveError = ref('')

const selectedEntityId = ref<string | null>(null)
const panelMode = ref<'view' | 'newEntity' | 'newRelation'>('view')

const editName = ref('')
const editType = ref<KgEntityType>('人物')
const editPropsText = ref('')

const newRelSubject = ref('')
const newRelPredicate = ref('')
const newRelObject = ref('')
const newRelObjectLiteral = ref('')
const useLiteralObject = ref(false)

const kg = computed(() => mvuStore.knowledgeGraph)

const activeEntities = computed(() =>
  (kg.value?.entities ?? []).filter((e) => !e.deleted),
)

const selectedEntity = computed(() =>
  activeEntities.value.find((e) => e.id === selectedEntityId.value) ?? null,
)

const relatedRelations = computed(() => {
  const id = selectedEntityId.value
  if (!id || !kg.value) return []
  return (kg.value.relations ?? []).filter((r) => r.subject === id || r.object === id)
})

const entitySelectOptions = computed(() =>
  activeEntities.value.map((e) => ({ label: `${e.name} (${e.type})`, value: e.id })),
)

const statsLabel = computed(() => {
  const n = countActiveEntities(kg.value)
  const m = countRelations(kg.value)
  return `${n} 个实体 · ${m} 条关系`
})

function close() {
  emit('update:show', false)
}

function applyKgFromResponse(data: KnowledgeGraphResponse) {
  if (data.knowledgeGraph) mvuStore.knowledgeGraph = data.knowledgeGraph
}

async function refresh() {
  if (!props.chatId) return
  loading.value = true
  saveError.value = ''
  try {
    await mvuStore.fetchKnowledgeGraph(props.chatId)
    await nextTick()
    rebuildNetwork()
  } finally {
    loading.value = false
  }
}

function destroyNetwork() {
  if (network.value) {
    network.value.destroy()
    network.value = null
  }
}

function rebuildNetwork() {
  destroyNetwork()
  const el = graphContainer.value
  if (!el || !props.show) return
  const { nodes, edges } = knowledgeGraphToVisData(kg.value)
  const data = {
    nodes: new DataSet(nodes),
    edges: new DataSet(edges),
  }
  network.value = new Network(el, data, {
    physics: {
      enabled: true,
      stabilization: { iterations: 120 },
    },
    interaction: { hover: true },
    edges: {
      font: { size: 11, color: 'var(--color-text-secondary)', strokeWidth: 0 },
      color: { color: 'var(--color-border)', highlight: 'var(--color-brand)' },
    },
    nodes: {
      font: { size: 14, color: 'var(--color-text)' },
      borderWidth: 1,
    },
  })
  network.value.on('click', (params) => {
    if (params.nodes.length === 1) {
      const id = String(params.nodes[0])
      if (!id.startsWith('__literal__')) {
        selectEntity(id)
      }
    }
  })
}

function selectEntity(id: string) {
  selectedEntityId.value = id
  panelMode.value = 'view'
  const e = activeEntities.value.find((x) => x.id === id)
  if (e) {
    editName.value = e.name
    editType.value = e.type
    editPropsText.value = Object.entries(e.properties ?? {})
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n')
  }
}

function parseProperties(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const t = line.trim()
    if (!t) continue
    const idx = t.indexOf(':')
    if (idx === -1) {
      out[t] = ''
    } else {
      out[t.slice(0, idx).trim()] = t.slice(idx + 1).trim()
    }
  }
  return out
}

async function saveEntity() {
  if (!props.chatId) return
  saveError.value = ''
  try {
    const body = {
      name: editName.value.trim(),
      type: editType.value,
      properties: parseProperties(editPropsText.value),
      entityId: selectedEntityId.value,
      expectedVersion: kg.value?.version,
    }
    const data = await apiPost<KnowledgeGraphResponse & { entityId?: string }>(
      `/api/mvu/${props.chatId}/knowledge-graph/entities`,
      body,
    )
    applyKgFromResponse(data)
    if (data.entityId) selectedEntityId.value = data.entityId
    panelMode.value = 'view'
    await nextTick()
    rebuildNetwork()
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : String(e)
  }
}

async function deleteSelectedEntity() {
  if (!props.chatId || !selectedEntityId.value) return
  if (!confirm('确定删除该实体？相关关系将一并移除。')) return
  saveError.value = ''
  try {
    await apiDelete(`/api/mvu/${props.chatId}/knowledge-graph/entities/${selectedEntityId.value}`)
    selectedEntityId.value = null
    panelMode.value = 'view'
    await refresh()
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : String(e)
  }
}

function startNewEntity() {
  panelMode.value = 'newEntity'
  selectedEntityId.value = null
  editName.value = ''
  editType.value = '人物'
  editPropsText.value = ''
}

function startNewRelation() {
  panelMode.value = 'newRelation'
  newRelSubject.value = selectedEntityId.value ?? ''
  newRelPredicate.value = ''
  newRelObject.value = ''
  newRelObjectLiteral.value = ''
  useLiteralObject.value = false
}

async function saveRelation() {
  if (!props.chatId) return
  const objectId = useLiteralObject.value
    ? newRelObjectLiteral.value.trim()
    : newRelObject.value
  if (!newRelSubject.value || !newRelPredicate.value.trim() || !objectId) {
    saveError.value = '请填写主体、谓语与客体'
    return
  }
  saveError.value = ''
  try {
    const data = await apiPost<KnowledgeGraphResponse>(
      `/api/mvu/${props.chatId}/knowledge-graph/relations`,
      {
        subjectId: newRelSubject.value,
        predicate: newRelPredicate.value.trim(),
        objectId,
        confidence: 1,
        expectedVersion: kg.value?.version,
      },
    )
    applyKgFromResponse(data)
    panelMode.value = 'view'
    await nextTick()
    rebuildNetwork()
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : String(e)
  }
}

async function deleteRelation(rel: { subject: string; predicate: string; object: string }) {
  if (!props.chatId) return
  saveError.value = ''
  try {
    const r = await fetch(`/api/mvu/${props.chatId}/knowledge-graph/relations`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subjectId: rel.subject,
        predicate: rel.predicate,
        objectId: rel.object,
        expectedVersion: kg.value?.version,
      }),
    })
    if (!r.ok) throw new Error(await r.text())
    const data = (await r.json()) as KnowledgeGraphResponse
    applyKgFromResponse(data)
    await nextTick()
    rebuildNetwork()
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : String(e)
  }
}

watch(
  () => props.show,
  async (open) => {
    if (open && props.chatId) {
      await refresh()
    } else {
      destroyNetwork()
      selectedEntityId.value = null
      panelMode.value = 'view'
    }
  },
)

watch(
  () => kg.value?.version,
  () => {
    if (props.show) void nextTick(() => rebuildNetwork())
  },
)

onUnmounted(() => destroyNetwork())
</script>

<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 z-[200] flex items-center justify-center p-4 pointer-events-auto"
      role="dialog"
      aria-modal="true"
      aria-label="知识图谱"
    >
      <div
        class="absolute inset-0 bg-black/50"
        @click="close"
      />
      <div
        class="relative flex flex-col w-[min(1100px,calc(100vw-2rem))] h-[min(720px,calc(100vh-2rem))] theme-panel-bg border border-[var(--color-border)] rounded-2xl shadow-glass-panel overflow-hidden"
      >
        <header class="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--color-border-subtle)] shrink-0">
          <div class="min-w-0">
            <h2 class="text-sm font-semibold text-[var(--color-text)]">知识图谱</h2>
            <p class="text-xs text-[var(--color-text-muted)] mt-0.5">{{ statsLabel }}</p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button type="button" class="btn btn-xs btn-secondary" :disabled="loading" @click="refresh">
              <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
              刷新
            </button>
            <button type="button" class="btn btn-xs btn-secondary" @click="startNewEntity">
              <Plus class="w-3.5 h-3.5" />
              新建实体
            </button>
            <button
              type="button"
              class="btn btn-xs btn-secondary"
              :disabled="activeEntities.length < 1"
              @click="startNewRelation"
            >
              新建关系
            </button>
            <button type="button" class="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]" aria-label="关闭" @click="close">
              <X class="w-4 h-4" />
            </button>
          </div>
        </header>

        <p v-if="saveError" class="px-4 py-2 text-xs text-error shrink-0 border-b border-[var(--color-border-subtle)]">{{ saveError }}</p>

        <div class="flex flex-1 min-h-0">
          <div
            ref="graphContainer"
            class="flex-1 min-w-0 bg-[var(--color-surface-muted)]"
          />
          <aside class="w-[min(320px,40%)] shrink-0 border-l border-[var(--color-border-subtle)] flex flex-col overflow-y-auto p-4 space-y-3">
            <div v-if="activeEntities.length === 0 && panelMode === 'view'" class="text-xs text-[var(--color-text-muted)] space-y-2">
              <p>暂无实体。MVU 会在对话中自动维护图谱，也可手动添加。</p>
              <button type="button" class="btn btn-sm btn-primary w-full" @click="startNewEntity">添加首个实体</button>
            </div>

            <template v-else-if="panelMode === 'newEntity' || (panelMode === 'view' && selectedEntity)">
              <div class="text-xs font-medium text-[var(--color-text-secondary)]">
                {{ panelMode === 'newEntity' ? '新建实体' : '实体详情' }}
              </div>
              <label class="block space-y-1">
                <span class="text-xs text-[var(--color-text-muted)]">名称</span>
                <input v-model="editName" type="text" class="input w-full" />
              </label>
              <label class="block space-y-1">
                <span class="text-xs text-[var(--color-text-muted)]">类型</span>
                <ModernSelect
                  :model-value="editType"
                  :options="KG_ENTITY_TYPES.map((t) => ({ label: t, value: t }))"
                  class="w-full"
                  @select="(opt) => { editType = (typeof opt === 'string' ? opt : String(opt.value)) as KgEntityType }"
                />
              </label>
              <label class="block space-y-1">
                <span class="text-xs text-[var(--color-text-muted)]">属性（每行 键: 值）</span>
                <textarea v-model="editPropsText" rows="4" class="input w-full text-xs font-mono" />
              </label>
              <div class="flex gap-2">
                <button type="button" class="btn btn-sm btn-primary flex-1" @click="saveEntity">保存</button>
                <button
                  v-if="panelMode === 'view'"
                  type="button"
                  class="btn btn-sm btn-secondary"
                  @click="panelMode = 'view'"
                >
                  取消
                </button>
              </div>
              <button
                v-if="selectedEntity && panelMode === 'view'"
                type="button"
                class="btn btn-sm btn-secondary w-full text-error"
                @click="deleteSelectedEntity"
              >
                <Trash2 class="w-3.5 h-3.5" />
                删除实体
              </button>

              <div v-if="selectedEntity && panelMode === 'view'" class="pt-2 border-t border-[var(--color-border-subtle)] space-y-2">
                <div class="text-xs font-medium text-[var(--color-text-secondary)]">关联关系</div>
                <div v-if="relatedRelations.length === 0" class="text-xs text-[var(--color-text-muted)]">暂无关系</div>
                <div
                  v-for="(rel, i) in relatedRelations"
                  :key="i"
                  class="flex items-start justify-between gap-2 text-xs text-[var(--color-text-secondary)]"
                >
                  <span class="min-w-0 break-words">{{ rel.predicate }} → {{ rel.object }}</span>
                  <button type="button" class="shrink-0 text-error hover:underline" @click="deleteRelation(rel)">删</button>
                </div>
              </div>
            </template>

            <template v-else-if="panelMode === 'newRelation'">
              <div class="text-xs font-medium text-[var(--color-text-secondary)]">新建关系</div>
              <label class="block space-y-1">
                <span class="text-xs text-[var(--color-text-muted)]">主体</span>
                <ModernSelect
                  :model-value="newRelSubject"
                  :options="entitySelectOptions"
                  placeholder="选择实体"
                  class="w-full"
                  @select="(opt) => { newRelSubject = typeof opt === 'string' ? opt : String(opt.value) }"
                />
              </label>
              <label class="block space-y-1">
                <span class="text-xs text-[var(--color-text-muted)]">谓语</span>
                <input v-model="newRelPredicate" type="text" class="input w-full" placeholder="如：信任、位于" />
              </label>
              <label class="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                <input v-model="useLiteralObject" type="checkbox" class="checkbox" />
                客体为字面量（非实体）
              </label>
              <label v-if="!useLiteralObject" class="block space-y-1">
                <span class="text-xs text-[var(--color-text-muted)]">客体实体</span>
                <ModernSelect
                  :model-value="newRelObject"
                  :options="entitySelectOptions"
                  placeholder="选择实体"
                  class="w-full"
                  @select="(opt) => { newRelObject = typeof opt === 'string' ? opt : String(opt.value) }"
                />
              </label>
              <label v-else class="block space-y-1">
                <span class="text-xs text-[var(--color-text-muted)]">客体字面量</span>
                <input v-model="newRelObjectLiteral" type="text" class="input w-full" />
              </label>
              <div class="flex gap-2">
                <button type="button" class="btn btn-sm btn-primary flex-1" @click="saveRelation">保存</button>
                <button type="button" class="btn btn-sm btn-secondary" @click="panelMode = 'view'">取消</button>
              </div>
            </template>

            <div v-else-if="panelMode === 'view' && !selectedEntity" class="text-xs text-[var(--color-text-muted)]">
              点击图中节点查看详情，或使用上方按钮新建。
            </div>
          </aside>
        </div>
      </div>
    </div>
  </Teleport>
</template>
