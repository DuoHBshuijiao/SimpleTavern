<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <label class="label">
        <span>初始状态栏</span>
        <span class="opacity-60 text-xs ml-2">新会话自动写入</span>
      </label>
      <button type="button" class="btn btn-xs btn-secondary" @click="addTable">新建表格</button>
    </div>

    <div
      v-if="!tables.length"
      class="text-xs text-[var(--color-text-muted)] border border-dashed border-[var(--color-border-subtle)] rounded-lg px-3 py-2"
    >
      暂无状态表格。新建表格后，新会话将自带初始状态栏。
    </div>

    <div
      v-for="(table, ti) in tables"
      :key="ti"
      class="rounded-lg border border-[var(--color-border-subtle)] bg-surface-muted p-3 space-y-2"
    >
      <div class="flex items-center gap-2 flex-wrap">
        <input v-model="table.name" class="input flex-1 text-sm min-w-[120px]" placeholder="表格名称" />
        <button type="button" class="btn btn-xs btn-secondary" @click="addColumn(ti)">+列</button>
        <button type="button" class="btn btn-xs btn-secondary" @click="addRow(ti)">+行</button>
        <button type="button" class="btn btn-xs btn-secondary text-red-400" @click="removeTable(ti)">删除</button>
      </div>

      <!-- 列标签 -->
      <div v-if="table.columns.length" class="flex flex-wrap gap-1">
        <span
          v-for="(_col, ci) in table.columns"
          :key="ci"
          class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--color-brand-a15)] text-[var(--color-brand)]"
        >
          <input
            v-model="table.columns[ci]"
            class="bg-transparent border-none outline-none text-[10px] w-[60px] text-[var(--color-brand)]"
            placeholder="列名"
          />
          <button type="button" class="hover:text-red-400 shrink-0 leading-none" @click="removeColumn(ti, ci)">&times;</button>
        </span>
      </div>

      <!-- 数据网格 -->
      <div v-if="table.columns.length && table.rows.length" class="overflow-x-auto -mx-1">
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr>
              <th class="text-left p-1.5 text-[var(--color-text-muted)] font-medium border-b border-[var(--color-border-subtle)] w-[80px]">字段</th>
              <th
                v-for="col in table.columns"
                :key="col"
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
                />
              </td>
              <td v-for="col in table.columns" :key="col" class="p-1 border-b border-[var(--color-border-subtle)]">
                <input
                  :model-value="row.cells[col] ?? ''"
                  @input="(e) => setCell(row, col, (e.target as HTMLInputElement).value)"
                  class="input text-xs py-0.5 px-1 w-full min-w-[60px]"
                  :placeholder="col"
                />
              </td>
              <td class="p-1 border-b border-[var(--color-border-subtle)]">
                <button type="button" class="text-[var(--color-text-muted)] hover:text-red-400 text-xs leading-none" @click="removeRow(ti, ri)">&times;</button>
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
import type { StatusTableDef, StatusTableRow } from '../../types/models'

const props = defineProps<{
  tables: StatusTableDef[]
}>()

const emit = defineEmits<{
  'update:tables': [tables: StatusTableDef[]]
}>()

function emitUpdate() {
  emit('update:tables', [...props.tables])
}

function cloneTable(t: StatusTableDef): StatusTableDef {
  return {
    name: t.name,
    columns: [...t.columns],
    rows: t.rows.map((r) => ({ field: r.field, cells: { ...r.cells } })),
  }
}

function setCell(row: StatusTableRow, col: string, value: string) {
  row.cells = { ...row.cells, [col]: value }
  emitUpdate()
}

function addTable() {
  const updated = [...props.tables, { name: '', columns: [], rows: [] }]
  emit('update:tables', updated)
}

function removeTable(ti: number) {
  const updated = [...props.tables]
  updated.splice(ti, 1)
  emit('update:tables', updated)
}

function addColumn(ti: number) {
  const updated = [...props.tables]
  const table = cloneTable(updated[ti]!)
  table.columns.push(`列${table.columns.length + 1}`)
  const colName = table.columns[table.columns.length - 1]!
  table.rows = table.rows.map((r) => {
    const cells = { ...r.cells }
    if (!(colName in cells)) cells[colName] = ''
    return { field: r.field, cells }
  })
  updated[ti] = table
  emit('update:tables', updated)
}

function removeColumn(ti: number, ci: number) {
  const updated = [...props.tables]
  const table = cloneTable(updated[ti]!)
  const removedCol = table.columns[ci]!
  table.columns.splice(ci, 1)
  table.rows = table.rows.map((r) => {
    const cells = { ...r.cells }
    delete cells[removedCol]
    return { field: r.field, cells }
  })
  updated[ti] = table
  emit('update:tables', updated)
}

function addRow(ti: number) {
  const updated = [...props.tables]
  const table = cloneTable(updated[ti]!)
  const cells: Record<string, string> = {}
  for (const col of table.columns) {
    cells[col] = ''
  }
  table.rows.push({ field: '', cells })
  updated[ti] = table
  emit('update:tables', updated)
}

function removeRow(ti: number, ri: number) {
  const updated = [...props.tables]
  const table = cloneTable(updated[ti]!)
  table.rows.splice(ri, 1)
  updated[ti] = table
  emit('update:tables', updated)
}
</script>
