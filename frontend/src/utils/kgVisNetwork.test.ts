import { describe, expect, it } from 'vitest'
import type { KnowledgeGraph } from '../types/models'
import { countActiveEntities, getKgEntityColor, knowledgeGraphToVisData } from './kgVisNetwork'

describe('kgVisNetwork', () => {
  it('filters deleted entities from vis nodes', () => {
    const kg: KnowledgeGraph = {
      entities: [
        { id: 'a', name: 'Active', type: '人物', properties: {} },
        { id: 'b', name: 'Gone', type: '地点', properties: {}, deleted: true },
      ],
      relations: [],
      version: 1,
      updatedAt: '',
      source: 'mvu_agent',
    }
    const { nodes, edges } = knowledgeGraphToVisData(kg)
    expect(nodes).toHaveLength(1)
    expect(nodes[0]?.id).toBe('a')
    expect(edges).toHaveLength(0)
    expect(countActiveEntities(kg)).toBe(1)
  })

  it('maps entity type to color field when document exists', () => {
    const c = getKgEntityColor('人物')
    expect(typeof c).toBe('string')
  })
})
