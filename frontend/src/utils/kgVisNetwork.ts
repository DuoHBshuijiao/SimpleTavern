/**
 * 知识图谱 → vis-network 数据转换与颜色映射。
 */
import type { KgEntity, KgEntityType, KnowledgeGraph } from '../types/models'

export const KG_ENTITY_TYPES: KgEntityType[] = ['人物', '地点', '物品', '势力', '事件']

const TYPE_COLOR_VAR: Record<KgEntityType, string> = {
  人物: '--color-brand',
  地点: '--color-success',
  物品: '--color-warning',
  势力: '--color-error',
  事件: '--color-text-muted',
}

/** 从 CSS 变量读取实体类型对应颜色（深浅主题自适应） */
export function getKgEntityColor(type: KgEntityType): string {
  if (typeof document === 'undefined') return ''
  const v = getComputedStyle(document.documentElement).getPropertyValue(TYPE_COLOR_VAR[type]).trim()
  return v || ''
}

export interface KgVisNode {
  id: string
  label: string
  title?: string
  color?: { background: string; border: string; highlight?: { background: string; border: string } }
}

export interface KgVisEdge {
  id: string
  from: string
  to: string
  label?: string
  arrows?: string
}

export interface KgVisData {
  nodes: KgVisNode[]
  edges: KgVisEdge[]
}

function activeEntities(kg: KnowledgeGraph): KgEntity[] {
  return (kg.entities ?? []).filter((e) => !e.deleted)
}

/** 将 KnowledgeGraph 转为 vis-network 节点/边（过滤已删除实体） */
export function knowledgeGraphToVisData(kg: KnowledgeGraph | null): KgVisData {
  if (!kg) return { nodes: [], edges: [] }
  const entities = activeEntities(kg)
  const entityIds = new Set(entities.map((e) => e.id))

  const nodes: KgVisNode[] = entities.map((e) => {
    const bg = getKgEntityColor(e.type)
    const props = Object.entries(e.properties ?? {})
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n')
    return {
      id: e.id,
      label: e.name,
      title: props ? `${e.type}\n${props}` : e.type,
      color: bg
        ? {
            background: bg,
            border: bg,
            highlight: { background: bg, border: bg },
          }
        : undefined,
    }
  })

  const edges: KgVisEdge[] = []
  let edgeIdx = 0
  for (const r of kg.relations ?? []) {
    if (!entityIds.has(r.subject)) continue
    const to = entityIds.has(r.object) ? r.object : r.object
    if (!entityIds.has(r.object)) {
      const literalId = `__literal__${edgeIdx}`
      nodes.push({
        id: literalId,
        label: r.object,
        title: '字面量',
        color: {
          background: getKgEntityColor('事件'),
          border: getKgEntityColor('事件'),
        },
      })
      edges.push({
        id: `e${edgeIdx}`,
        from: r.subject,
        to: literalId,
        label: r.predicate,
        arrows: 'to',
      })
    } else {
      edges.push({
        id: `e${edgeIdx}`,
        from: r.subject,
        to,
        label: r.predicate,
        arrows: 'to',
      })
    }
    edgeIdx += 1
  }

  return { nodes, edges }
}

export function countActiveEntities(kg: KnowledgeGraph | null): number {
  if (!kg) return 0
  return activeEntities(kg).length
}

export function countRelations(kg: KnowledgeGraph | null): number {
  if (!kg) return 0
  return (kg.relations ?? []).length
}
