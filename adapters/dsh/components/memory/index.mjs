import { Service } from '@deepseek-ai/cordis'

/** Optional provider capability; no routing, ambient retrieval, or credential storage. */
export default class ThalirisMemory extends Service {
  constructor(ctx) { super(ctx, 'thalirisMemory'); this.providers = new Map() }
  register(owner, provider) {
    if (!provider?.id || ['read', 'search', 'write'].some(key => typeof provider[key] !== 'function') || this.providers.has(provider.id)) throw new Error('THALIRIS_INVALID_MEMORY_PROVIDER')
    return owner.effect(() => {
      this.providers.set(provider.id, provider)
      return () => { if (this.providers.get(provider.id) === provider) this.providers.delete(provider.id) }
    })
  }
  list() { return [...this.providers.values()].map(({ id, name }) => ({ id, name: name ?? id })) }
  async invoke(id, operation, request) {
    const provider = this.providers.get(id)
    if (!provider) throw new Error('THALIRIS_MEMORY_PROVIDER_UNAVAILABLE')
    request.signal.throwIfAborted()
    const value = await provider[operation](request)
    request.signal.throwIfAborted()
    if (this.providers.get(id) !== provider) throw new Error('THALIRIS_MEMORY_PROVIDER_UNAVAILABLE')
    const result = JSON.parse(JSON.stringify(value))
    if (Buffer.byteLength(JSON.stringify(result), 'utf8') > request.maxBytes) throw new Error('THALIRIS_MEMORY_RESULT_BOUND_EXCEEDED')
    return result
  }
}
