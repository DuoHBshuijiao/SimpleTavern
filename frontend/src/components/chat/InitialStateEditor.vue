<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <label class="label">
        <span>初始状态栏</span>
        <span v-if="props.subtitle" class="opacity-60 text-xs ml-2">{{ props.subtitle }}</span>
      </label>
      <button type="button" class="btn btn-xs btn-secondary" @click="addTable">新建表格</button>
    </div>

    <div
      v-if="!localTables.length"
      class="text-xs text-[var(--color-text-muted)] border border-dashed border-[var(--color-border-subtle)] rounded-lg px-3 py-2"
    >
      {{ props.emptyHint }}
    </div>

    <div
      v-for="(table, ti) in localTables"
      :key="ti"
      class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-3 space-y-2"
    >
      <div class="flex items-center gap-2 flex-wrap">
        <input v-model="table.name" class="input flex-1 text-sm min-w-[120px]" placeholder="表格名称" @input="emitUpdate" />
        <button type="button" class="btn btn-xs btn-secondary" @click="addColumn(ti)">+列</button>
        <button type="button" class="btn btn-xs btn-secondary" @click="addRow(ti)">+行</button>
        <button type="button" class="btn btn-xs btn-danger" @click="removeTable(ti)">删除</button>
      </div>

      <div v-if="table.columns.length" class="flex flex-wrap gap-1">
        <span
          v-for="(_col, ci) in table.columns"
          :key="ci"
          class="inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded-full bg-[var(--color-brand-a15)] text-[var(--color-brand)]"
        >
          <input
            class="bg-transparent border-none outline-none text-2xs w-[60px] text-[var(--color-brand)]"
            placeholder="列名"
            :value="table.columns[ci]"
            @input="onColumnNameInput(ti, ci, $event)"
          />
          <button type="button" class="shrink-0 leading-none text-[var(--color-text-muted)] hover:text-[var(--color-error-text)] transition-colors" @click="removeColumn(ti, ci)">&times;</button>
        </span>
      </div>

      <div v-if="table.columns.length && table.rows.length" class="overflow-x-auto -mx-1">
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr>
              <th class="text-left p-1.5 text-[var(--color-text-muted)] font-medium border-b border-[var(--color-border-subtle)] w-[80px]">字段</th>
              <th
                v-for="(col, hci) in table.columns"
                :key="hci"
                class="text-left p-1.5 text-[var(--color-text-muted)] font-medium border-b border-[var(--color-border-subtle)]"
              >{{ col }}</th>
              <th class="w-6 border-b border-[var(--color-border-subtle)]" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in table.rows" :key="ri">
              <td class="p-1 border-b border-[var(--color-border-subtle)]">
                <input
                  v-model="row.field"
                  class="input text-xs py-0.5 px-1 w-full min-w-[60px]"
                  placeholder="字段"
                  @input="emitUpdate"
                />
              </td>
              <td v-for="(col, hci) in table.columns" :key="hci" class="p-1 border-b border-[var(--color-border-subtle)]">
                <input
                  v-model="row.cells[col]"
                  class="input text-xs py-0.5 px-1 w-full min-w-[60px]"
                  :placeholder="col"
                  @input="emitUpdate"
                />
              </td>
              <td class="p-1 border-b border-[var(--color-border-subtle)]">
                <button type="button" class="text-[var(--color-text-muted)] hover:text-[var(--color-error-text)] text-xs leading-none transition-colors" @click="removeRow(ti, ri)">&times;</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-xs text-[var(--color-text-muted)]">
        请先添加列和行。
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { StatusTableDef } from '../../types/models'

const props = withDefaults(defineProps<{
  tables: StatusTableDef[]
  /** 副标题（默认沿用「新会话自动写入」；传空字符串可隐藏） */
  subtitle?: string
  /** 空状态提示文案 */
  emptyHint?: string
}>(), {
  subtitle: '新会话自动写入',
  emptyHint: '暂无状态表格。新建表格后，新会话将自带初始状态栏。',
})

const emit = defineEmits<{
  'update:tables': [tables: StatusTableDef[]]
}>()

function deepClone(t: StatusTableDef[]): StatusTableDef[] {
  return t.map((tbl) => ({
    name: tbl.name,
    columns: [...tbl.columns],
    rows: tbl.rows.map((r) => {
      const cells: Record<string, string> = {}
      for (const col of tbl.columns) {
        cells[col] = (r.cells && r.cells[col]) ? r.cells[col] : ''
      }
      return { field: r.field, cells }
    }),
  }))
}

const localTables = reactive<StatusTableDef[]>(deepClone(props.tables))

watch(() => props.tables, (val) => {
  const cloned = deepClone(val)
  localTables.length = 0
  for (const t of cloned) {
    localTables.push(t)
  }
}, { deep: true })

function emitUpdate() {
  emit('update:tables', JSON.parse(JSON.stringify(localTables)))
}

/** 列名变更时同步迁移每行 cells 的键，避免 v-model 只改 columns 导致数据挂在旧键上 */
function onColumnNameInput(ti: number, ci: number, e: Event) {
  const el = e.target
  if (!(el instanceof HTMLInputElement)) return
  const newName = el.value
  const table = localTables[ti]!
  const oldName = table.columns[ci] ?? ''
  if (oldName === newName) {
    emitUpdate()
    return
  }
  table.columns[ci] = newName
  if (oldName !== '') {
    for (const r of table.rows) {
      if (Object.prototype.hasOwnProperty.call(r.cells, oldName)) {
        const v = r.cells[oldName]!
        delete r.cells[oldName]
        r.cells[newName] = v
      }
    }
  }
  emitUpdate()
}

function addTable() {
  localTables.push({ name: '', columns: [], rows: [] })
  emitUpdate()
}

function removeTable(ti: number) {
  localTables.splice(ti, 1)
  emitUpdate()
}

function addColumn(ti: number) {
  const table = localTables[ti]!
  const colName = `列${table.columns.length + 1}`
  table.columns.push(colName)
  for (const r of table.rows) {
    r.cells[colName] = ''
  }
  emitUpdate()
}

function removeColumn(ti: number, ci: number) {
  const table = localTables[ti]!
  const removedCol = table.columns[ci]!
  table.columns.splice(ci, 1)
  for (const r of table.rows) {
    delete r.cells[removedCol]
  }
  emitUpdate()
}

function addRow(ti: number) {
  const table = localTables[ti]!
  const cells: Record<string, string> = {}
  for (const col of table.columns) {
    cells[col] = ''
  }
  table.rows.push({ field: '', cells })
  emitUpdate()
}

function removeRow(ti: number, ri: number) {
  localTables[ti]!.rows.splice(ri, 1)
  emitUpdate()
}
</script>
