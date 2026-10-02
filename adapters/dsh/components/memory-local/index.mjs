import z from '@deepseek-ai/schemastery'
import { z as schema } from 'zod'
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'

export const name = 'thaliris-memory-local'
export const inject = ['thalirisMemory', 'storageDomain']
export const Config = z.object({ providerId: z.string().default('thaliris-local') })
const spec = defineDomain({ name: 'thaliris_memory_local', version: 1,
  tables: { entries: domainTable(schema.object({ workspaceId: schema.string(), key: schema.string(), text: schema.string(), provenance: schema.string() })) } })
export async function apply(ctx, config) {
  const domain = await ctx.storageDomain.open(spec)
  ctx.effect(() => () => domain.close())
  const table = domain.table('entries')
  const entries = workspaceId => [...table.entries()].map(([, value]) => value).filter(value => value.workspaceId === workspaceId)
  ctx.thalirisMemory.register(ctx, {
    id: config.providerId, name: 'Local Thaliris memory',
    async read({ workspaceId, key }) { return entries(workspaceId).find(entry => entry.key === key) ?? null },
    async search({ workspaceId, query, limit }) { return entries(workspaceId).filter(entry => entry.text.includes(query) || entry.key.includes(query)).slice(0, limit) },
    async write({ workspaceId, key, text, provenance }) {
      await table.put(JSON.stringify([workspaceId, key]), { workspaceId, key, text, provenance })
      return { key, stored: true }
    },
  })
}
