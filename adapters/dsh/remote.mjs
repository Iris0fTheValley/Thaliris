import { z } from 'zod'
// Native client contribution shape and strict inputs, matching api.mjs.
// Source: upstream TypertRemoteContribution and Gateway requireStrictInputs.
const method = (name, parameters, cancellable = false) => ({
  id: `@thaliris/dsh-plugin#thaliris/${name}`, service: 'thalirisController', namespace: 'thaliris', method: name,
  invocation: { kind: 'direct' },
  parameters: parameters.map(name => ({ name, wire: name, source: 'json', codec: { mode: 'strict', typeSymbol: '@thaliris/dsh-plugin#NativeIdentity', create: () => z.string().trim().min(1).max(128) } })),
  ...(cancellable ? { cancellation: { parameter: 'signal' } } : {}), result: { mode: 'strict', typeSymbol: '@thaliris/dsh-plugin#JsonValue', create: () => z.json(), decode: value => z.json().parse(value) },
})
export const remoteContribution = { package: '@thaliris/dsh-plugin', descriptors: [
  method('templates', []), method('providers', []), method('diagnostics', ['sessionId'], true),
  method('approveMemory', ['sessionId', 'proposalId'], true),
] }
