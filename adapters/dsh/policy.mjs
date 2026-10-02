import z from '@deepseek-ai/schemastery'

export const controllerTemplate = `Thaliris Controller contract:
You own task direction, scope, accepted invariants, and semantic completion. Models own semantics; the mechanical layer owns facts. Thaliris records selected intent and mechanical observations; it does not choose roles, judge work, or accept a task for you. For each semantic slice, decide under the selected execution mode whether you may handle the permitted work directly or should delegate. Delegate only when the slice calls for it; if delegating, select the minimum suitable role and send only a bounded handoff; do not send the parent transcript or full working set. Native completion is an observation, not acceptance.`
export const roleTemplates = [
  ['investigator', 'Investigator', 'Gather and verify facts within the selected scope. Return concise findings with locations, unknowns and contradictions.'],
  ['implementer', 'Implementer', 'Execute the accepted direction for this bounded slice. Verify changed behavior and synchronize assigned documentation.'],
  ['focused-implementer', 'Focused Implementer', 'Implement a coherent candidate across the assigned coupled invariants. Return decision-changing unknowns to the Controller.'],
  ['reviewer', 'Reviewer', 'Independently challenge the selected candidate with evidence; do not implement or decide acceptance.'],
  ['curator', 'Curator', 'Propose selected memory changes for user review. Do not change memory policy or task authority.'],
].map(([id, name, prompt]) => ({ id, name, description: `${name} initial template`, prompt, enabled: true,
  tools: [], modelPolicy: { mode: 'inherit', routes: [] }, memory: { read: [], write: [] }, context: { handoff: true, memory: false } }))
const route = z.object({ provider: z.string().required(), model: z.string().required(), reasoningEffort: z.string() })
export const roleSchema = z.object({
  id: z.string().required(), name: z.string().required(), description: z.string().default(''), prompt: z.string().default(''),
  enabled: z.boolean().default(true), tools: z.array(z.string()).default([]),
  modelPolicy: z.object({ mode: z.union(['inherit', 'fixed', 'allowed'].map(z.const)).default('inherit'), routes: z.array(route).default([]) }).default({ mode: 'inherit', routes: [] }),
  memory: z.object({ read: z.array(z.string()).default([]), write: z.array(z.string()).default([]) }).default({ read: [], write: [] }),
  context: z.object({ handoff: z.boolean().default(true), memory: z.boolean().default(false) }).default({ handoff: true, memory: false }),
})
export const Config = z.object({
  pythonExecutable: z.string().required(), corePath: z.string().required(), authorityDirectory: z.string().required(),
  subagentProvider: z.string().default('spawn'), bridgeTimeoutMs: z.number().min(1).max(300000).default(30000),
  policy: z.object({
    controllerPrompt: z.string().default(controllerTemplate),
    workspaces: z.array(z.object({ workspaceId: z.string().required(), root: z.string().required(), enabled: z.boolean().default(true) })).default([]),
    roles: z.array(roleSchema).default([]),
    memory: z.object({ mode: z.union(['disabled', 'manual', 'suggest-review', 'auto'].map(z.const)).default('disabled'),
      autoAuthorized: z.boolean().default(false), providers: z.array(z.string()).default([]),
      controllerRead: z.array(z.string()).default([]), controllerWrite: z.array(z.string()).default([]),
    }).default({ mode: 'disabled', autoAuthorized: false, providers: [], controllerRead: [], controllerWrite: [] }),
  }).default({}).volatile(),
})

export function readPolicy(config) {
  return structuredClone(config.policy.get())
}

/** Validate only the role selected for execution; unrelated stored roles do not gate lifecycle reads. */
export function selectedRole(policy, id) {
  const matches = policy.roles.filter(role => role.id === id)
  if (matches.length !== 1 || !matches[0].enabled) throw new Error('THALIRIS_ROLE_NOT_CONFIGURED')
  const role = matches[0]
  if (!role.id.trim() || role.tools.some(tool => tool.startsWith('thaliris_task_') || tool === 'thaliris_workstream' || tool === 'thaliris_reconcile')) throw new Error('THALIRIS_INVALID_ROLE_POLICY')
  if (role.modelPolicy.mode === 'fixed' && role.modelPolicy.routes.length !== 1) throw new Error('THALIRIS_FIXED_ROUTE_REQUIRED')
  return role
}
