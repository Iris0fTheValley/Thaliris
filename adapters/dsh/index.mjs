import { createHash, randomUUID } from 'node:crypto'
import { realpathSync } from 'node:fs'
import { isAbsolute } from 'node:path'
import { fileURLToPath } from 'node:url'
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools'
import { readPolicy } from './policy.mjs'
export { Config } from './policy.mjs'
export const name = 'thaliris-dsh'
export const inject = ['agents', 'systemPrompt', 'tools', 'subagents', 'subprocess', 'workspaceRegistry', 'sessionPersistence', 'llm']
export const TOOL_NAMES = Object.freeze(['thaliris_task_start', 'thaliris_task_inspect', 'thaliris_workstream', 'thaliris_task_close', 'thaliris_reconcile'])
export const MEMORY_TOOLS = Object.freeze(['thaliris_memory_read', 'thaliris_memory_search', 'thaliris_memory_propose'])
const bridgePath = fileURLToPath(new URL('./core_bridge.py', import.meta.url))
const string = { type: 'string' }
const object = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required, additionalProperties: false })
const contractSchema = object({ human_instruction: string, boundary: string, invariants: string, acceptance: string, execution_mode: { type: 'string', enum: ['delegated', 'controller-direct', 'single-agent'] } })
const handoffSchema = object({ goal: string, scope: string, invariants: string, acceptance: string, context: string })
const identitySchema = { task_id: string, base_revision: { type: 'integer' } }
const memoryContextSchema = { type: 'array', maxItems: 4, items: object({ provider: string, operation: { type: 'string', enum: ['read', 'search'] }, key: string, query: string, limit: { type: 'integer', minimum: 1, maximum: 20 }, maxBytes: { type: 'integer', minimum: 1, maximum: 16384 } }, ['provider', 'operation', 'maxBytes']) }
const routeSchema = object({ provider: string, model: string, reasoningEffort: string }, ['provider', 'model'])
function validate(parameters, args) {
  const errors = validateJsonSchemaValue(parameters, args)
  if (errors.length) throw new Error(`THALIRIS_INVALID_ARGUMENTS: ${errors.join('; ')}`)
  if (JSON.stringify(args).length > 65536) throw new Error('THALIRIS_ARGUMENT_BOUND_EXCEEDED')
  if (args.base_revision !== undefined && (!Number.isSafeInteger(args.base_revision) || args.base_revision < 1)) throw new Error('THALIRIS_REVISION_REQUIRED')
}

/** Native Settings owns mutable user policy. Core alone owns task intent. */
export function apply(ctx, config) {
  for (const key of ['pythonExecutable', 'corePath', 'authorityDirectory']) {
    if (typeof config[key] !== 'string' || !isAbsolute(config[key])) throw new Error(`THALIRIS_ABSOLUTE_CONFIG_REQUIRED: ${key}`)
  }
  readPolicy(config)
  const python = realpathSync(config.pythonExecutable), corePath = realpathSync(config.corePath)
  let disposed = false, tail = Promise.resolve(), bridgeTail = Promise.resolve()
  const cancellations = new Set(), operations = new Set(), runs = new Set(), childGrants = new WeakMap()
  function isNativeRoot(agent) {
    const header = agent?.session.header
    return !!agent && ctx.agents.get(agent.id) === agent && ctx.agents.roots().includes(agent)
      && header.id === agent.id && header.parentSession === undefined && header.isSeeded === false
      && (header.delegationDepth ?? 0) === 0 && header.origin !== 'subagent' && !!header.cwd
  }
  async function binding(agent) {
    if (disposed || !isNativeRoot(agent)) throw new Error('THALIRIS_NATIVE_ROOT_REQUIRED')
    const workspace = await ctx.workspaceRegistry.resolveByPath(agent.session.header.cwd)
    const selected = readPolicy(config).workspaces.find(row => row.enabled && row.workspaceId === workspace?.id)
    if (!selected || realpathSync(selected.root) !== realpathSync(workspace.path) || realpathSync(agent.session.header.cwd) !== realpathSync(selected.root)) throw new Error('THALIRIS_WORKSPACE_NOT_CONFIGURED')
    // Persistent native metadata, never a caller id or a matching object alone.
    const stored = await ctx.sessionPersistence.stat(agent.id)
    const header = stored?.header
    if (!header || header.id !== agent.id || header.parentSession !== undefined || header.isSeeded !== false
      || (header.delegationDepth ?? 0) !== 0 || header.origin === 'subagent' || !header.cwd
      || realpathSync(header.cwd) !== realpathSync(selected.root)) throw new Error('THALIRIS_PERSISTED_ROOT_REQUIRED')
    return { root: realpathSync(selected.root), workspaceId: workspace.id }
  }
  ctx.systemPrompt.section({ name: 'thaliris:controller-contract', order: ctx.systemPrompt.getSectionOrder('TEAM_POLICY'),
    text: ({ agent }) => {
      if (!isNativeRoot(agent)) return ''
      const policy = readPolicy(config)
      const cwd = realpathSync(agent.session.header.cwd)
      return policy.workspaces.some(row => row.enabled && realpathSync(row.root) === cwd && ctx.workspaceRegistry.get(row.workspaceId)?.path && realpathSync(ctx.workspaceRegistry.get(row.workspaceId).path) === cwd) ? policy.controllerPrompt : ''
    },
  })
  function bridge(agent, operation, args, signal) {
    const pending = bridgeTail.then(() => bridgeExecute(agent, operation, args, signal))
    bridgeTail = pending.catch(() => {})
    return pending
  }
  async function bridgeExecute(agent, operation, args, signal) {
    const bound = await binding(agent)
    signal.throwIfAborted()
    const deadline = new AbortController(), timer = setTimeout(() => deadline.abort('Thaliris bridge deadline exceeded'), config.bridgeTimeoutMs)
    timer.unref()
    const processSignal = AbortSignal.any([signal, deadline.signal])
    let command
    try {
      command = ctx.subprocess.spawn({ argv: [python, '-I', bridgePath], cwd: bound.root, graceMs: 1000, signal: processSignal,
        stdio: { stdin: { data: JSON.stringify({ protocol: 1, core_path: corePath, root: bound.root, authority_directory: config.authorityDirectory,
          native_controller_id: agent.id, native_workspace_id: bound.workspaceId, operation, arguments: args }) }, stdout: { maxBytes: 1048576 }, stderr: { maxBytes: 8192 } } })
      const outcome = await command.done, stdout = command.collected.stdout.readFrom(0)
      if (stdout.lossy) throw new Error('THALIRIS_BRIDGE_RESPONSE_TOO_LARGE')
      const response = JSON.parse(stdout.text)
      if (response.protocol !== 1 || response.ok !== true || outcome.exitCode !== 0) throw new Error(response.error ?? 'THALIRIS_BRIDGE_FAILED')
      processSignal.throwIfAborted()
      return response.result
    } finally { clearTimeout(timer); if (command) { command.terminate(); await command.waitForExit() } }
  }
  function register(toolName, description, parameters, body, childAllowed = false) {
    ctx.tools.register({ name: toolName, description, parameters,
      output: { schema: { type: 'object', additionalProperties: true }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
      async execute(args, exec) {
        if (disposed || ctx.agents.get(exec.agent?.id) !== exec.agent || (!isNativeRoot(exec.agent) && !(childAllowed && childGrants.has(exec.agent)))) throw new Error('THALIRIS_NATIVE_ROOT_REQUIRED')
        validate(parameters, args)
        const cancel = new AbortController(), signal = AbortSignal.any([exec.signal, cancel.signal])
        cancellations.add(cancel)
        const work = async () => { signal.throwIfAborted(); if (isNativeRoot(exec.agent)) await binding(exec.agent); return body(args, exec.agent, signal) }
        // Child memory calls cannot wait behind the Controller's child-result wait.
        const operation = childAllowed ? work() : tail.then(work)
        if (!childAllowed) tail = operation.catch(() => {})
        operations.add(operation)
        try { return await operation } finally { operations.delete(operation); cancellations.delete(cancel) }
      } })
  }
  register(TOOL_NAMES[0], 'Controller explicitly selects human intent. Native Settings is user policy, never task consent.', object({ goal: string, contract: contractSchema }),
    (args, agent, signal) => bridge(agent, 'start', args, signal))
  register(TOOL_NAMES[1], 'Inspect Core task and unresolved reservation without inferring outcomes.', object({}),
    (_args, agent, signal) => bridge(agent, 'inspect', {}, signal))
  register(TOOL_NAMES[2], 'Select one editable role and bounded handoff for a fresh native child.', object({ ...identitySchema, workstream: string, role: string, handoff: handoffSchema, route: routeSchema, memoryContext: memoryContextSchema }, [...Object.keys(identitySchema), 'workstream', 'role', 'handoff']), async (args, agent, signal) => {
    const policy = readPolicy(config), role = policy.roles.find(row => row.id === args.role && row.enabled)
    if (!role) throw new Error('THALIRIS_ROLE_NOT_CONFIGURED')
    if (!role.context.handoff) throw new Error('THALIRIS_ROLE_HANDOFF_DENIED')
    const provider = ctx.subagents.getProvider(config.subagentProvider)
    if (!provider || provider.inheritsParentContext !== false) throw new Error('THALIRIS_FRESH_PROVIDER_REQUIRED')
    let route
    const mode = role.modelPolicy.mode
    if (mode === 'inherit') { if (args.route) throw new Error('THALIRIS_MODEL_ROUTE_NOT_ALLOWED') }
    else {
      route = args.route ?? (mode === 'fixed' ? role.modelPolicy.routes[0] : undefined)
      if (!route || !role.modelPolicy.routes.some(candidate => candidate.provider === route.provider && candidate.model === route.model && candidate.reasoningEffort === route.reasoningEffort)) throw new Error('THALIRIS_MODEL_ROUTE_NOT_ALLOWED')
      const info = await ctx.llm.resolveModelInfo(route.provider, route.model, signal)
      if (route.reasoningEffort !== undefined && !info.reasoning?.efforts.some(effort => effort.id === route.reasoningEffort)) throw new Error('THALIRIS_MODEL_CAPABILITY_NOT_ALLOWED')
    }
    const inspected = await bridge(agent, 'inspect', {}, signal)
    if (inspected.contract.execution_mode !== 'delegated') throw new Error('THALIRIS_DELEGATED_INTENT_REQUIRED')
    const bound = await binding(agent)
    const selectedMemory = []
    for (const selection of args.memoryContext ?? []) {
      if (!role.context.memory || !role.memory.read.includes(selection.provider)) throw new Error('THALIRIS_MEMORY_PERMISSION_DENIED')
      if (selection.operation === 'read' && typeof selection.key !== 'string' || selection.operation === 'search' && (typeof selection.query !== 'string' || !Number.isSafeInteger(selection.limit))) throw new Error('THALIRIS_MEMORY_SELECTION_REQUIRED')
      selectedMemory.push({ selection, result: await memory(selection, agent, signal, selection.operation) })
    }
    const prompt = JSON.stringify({ workstream: args.workstream, role: role.id, ...args.handoff, ...(selectedMemory.length ? { memory_context: selectedMemory } : {}) })
    const selected = { workstream: args.workstream, role: role.id, handoff_sha256: createHash('sha256').update(prompt).digest('hex'), correlation: `thaliris:${randomUUID()}` }
    let begun = await bridge(agent, 'begin', { task_id: args.task_id, base_revision: args.base_revision, observation: JSON.stringify(selected) }, signal)
    let run
    try {
      run = await ctx.subagents.start(config.subagentProvider, { parent: agent, signal, label: selected.correlation, prompt: [{ type: 'text', text: prompt }], maxDepth: 1,
        toolFilter: { allow: role.tools, deny: TOOL_NAMES }, ...(route ? { agentOptions: route } : {}), persona: role.prompt })
      runs.add(run)
      if (!run.localAgent || run.localAgent.id !== run.id || run.localAgent.session.header.parentSession !== agent.id || run.localAgent.session.header.isSeeded !== false) throw new Error('THALIRIS_NATIVE_CHILD_IDENTITY_REQUIRED')
      childGrants.set(run.localAgent, { roleId: role.id, parent: agent, bound })
      // Commit observed ID immediately, before awaiting the result. Catalog label covers the preceding crash window.
      await ctx.sessionPersistence.flush()
      const beforeBind = await bridge(agent, 'inspect', {}, signal)
      begun = await bridge(agent, 'bind', { task_id: args.task_id, base_revision: beforeBind.state.revision, observation: JSON.stringify({ ...selected, child_id: run.id }) }, signal)
      const result = await run.result
      await ctx.sessionPersistence.flush()
      const observed = { ...selected, child_id: run.id, stop_reason: result.stopReason, provenance: 'native-run-result' }
      const beforeFinish = await bridge(agent, 'inspect', {}, signal)
      const ack = await bridge(agent, 'finish', { task_id: args.task_id, base_revision: beforeFinish.state.revision, observation: JSON.stringify(observed) }, signal)
      const value = { ...ack, child_id: run.id, stop_reason: result.stopReason, native_completed: result.stopReason === 'completed', output: result.output }
      if (result.stopReason !== 'completed') throw new Error('THALIRIS_NATIVE_CHILD_FAILED: ' + JSON.stringify(value))
      return value
    } finally { if (run) { if (run.localAgent) childGrants.delete(run.localAgent); await run.dispose(); runs.delete(run) } }
  })
  register(TOOL_NAMES[3], 'Controller decides semantic acceptance. Unresolved work blocks close.', object({ ...identitySchema, decision: string }),
    (args, agent, signal) => bridge(agent, 'close', args, signal))

  async function nativeObservation(agent, reservation, signal, cancel) {
    const own = agent.session.snapshotEvents().filter(event => event.type === 'subagent/catalog' && event.data.label === reservation.correlation)
    const ids = [...new Set(own.map(event => event.data.childId))]
    const id = reservation.child_id ?? (ids.length === 1 ? ids[0] : undefined)
    if (!id || ids.length !== 1 || ids[0] !== id) return { outcome: 'UNKNOWN', reason: 'native catalog correlation unresolved' }
    const live = ctx.agents.get(id)
    if (live) {
      if (live.session.header.parentSession !== agent.id) throw new Error('THALIRIS_NATIVE_CHILD_IDENTITY_REQUIRED')
      if (!cancel) return { child_id: id, outcome: 'UNKNOWN', reason: 'native child resident; cancel and observe or await its owner' }
      live.cancel({ kind: 'parent' })
      await live.whenIdle()
      await ctx.sessionPersistence.flush()
    }
    const handle = await ctx.sessionPersistence.open(id, 'read', { signal })
    try {
      if (handle.header.parentSession !== agent.id || handle.header.isSeeded !== false || handle.header.origin !== 'subagent'
        || realpathSync(handle.header.cwd) !== realpathSync(agent.session.header.cwd)) throw new Error('THALIRIS_NATIVE_CHILD_IDENTITY_REQUIRED')
      const { events } = await handle.read(0, undefined, { signal })
      const start = events.filter(event => event.type === 'turn/start').at(-1)
      const end = events.filter(event => event.type === 'turn/end').at(-1)
      if (!start || !end || end.seq < start.seq || !['completed', 'aborted', 'error', 'max-tokens', 'blocked', 'interrupted'].includes(end.data.reason.kind)) return { child_id: id, outcome: 'UNKNOWN', reason: 'durable native terminal reason unavailable' }
      return { child_id: id, outcome: end.data.reason.kind, terminal_seq: end.seq, terminal_reason: end.data.reason, provenance: 'native-session-turn/end' }
    } finally { await handle.close() }
  }
  register(TOOL_NAMES[4], 'Check/reconcile a crash reservation using native catalog and durable terminal Session evidence. UNKNOWN never auto releases.',
    object({ ...identitySchema, action: { type: 'string', enum: ['check', 'reconcile', 'cancel-reconcile'] } }), async (args, agent, signal) => {
      const inspected = await bridge(agent, 'inspect', {}, signal)
      if (inspected.state.task_id !== args.task_id || inspected.state.revision !== args.base_revision) throw new Error('TASK_ID_OR_REVISION_CONFLICT')
      if (inspected.state.active_work.length !== 1) throw new Error('THALIRIS_RESERVATION_REQUIRED')
      const reservation = JSON.parse(inspected.state.active_work[0])
      const observation = await nativeObservation(agent, reservation, signal, args.action === 'cancel-reconcile')
      if (args.action === 'check' || observation.outcome === 'UNKNOWN') return { ...observation, released: false }
      return { ...await bridge(agent, 'reconcile', { task_id: args.task_id, base_revision: args.base_revision, observation: JSON.stringify({ ...reservation, ...observation }) }, signal), ...observation, released: true, native_completed: observation.outcome === 'completed' }
    })

  async function memory(args, agent, signal, operation) {
    const policy = readPolicy(config), grant = childGrants.get(agent)
    const role = grant && policy.roles.find(row => row.id === grant.roleId && row.enabled)
    if (grant && (!role || !role.context.memory || !role.tools.includes(operation === 'read' ? MEMORY_TOOLS[0] : operation === 'search' ? MEMORY_TOOLS[1] : MEMORY_TOOLS[2]))) throw new Error('THALIRIS_MEMORY_PERMISSION_DENIED')
    const permission = operation === 'write' ? 'write' : 'read'
    const allowed = grant ? role.memory[permission] : policy.memory[permission === 'write' ? 'controllerWrite' : 'controllerRead']
    if (policy.memory.mode === 'disabled' || !policy.memory.providers.includes(args.provider) || !allowed.includes(args.provider)) throw new Error('THALIRIS_MEMORY_PERMISSION_DENIED')
    const bound = grant?.bound ?? await binding(agent)
    if (operation === 'write' && policy.memory.mode === 'auto' && policy.memory.autoAuthorized !== true) throw new Error('THALIRIS_MEMORY_AUTO_OPT_IN_REQUIRED')
    if (operation === 'write' && policy.memory.mode !== 'auto') {
      const parent = grant?.parent ?? agent
      const proposal = { proposal_id: randomUUID(), provider: args.provider, key: args.key, text: args.text, provenance: args.provenance, role: grant?.roleId ?? 'Controller', workspaceId: bound.workspaceId, policy: policy.memory.mode }
      const acknowledgement = await bridge(parent, 'proposal', { observation: JSON.stringify(proposal) }, signal)
      return { proposed: true, proposal_id: proposal.proposal_id, ...acknowledgement }
    }
    const capability = ctx.get('thalirisMemory')
    if (!capability) throw new Error('THALIRIS_MEMORY_CAPABILITY_UNAVAILABLE')
    return { value: await capability.invoke(args.provider, operation, { ...args, ...bound, signal, maxBytes: args.maxBytes ?? 16384 }) }
  }
  const bounds = { maxBytes: { type: 'integer', minimum: 1, maximum: 65536 } }
  register(MEMORY_TOOLS[0], 'Explicit bounded memory read under user provider and role grants.', object({ provider: string, key: string, ...bounds }), (args, agent, signal) => memory(args, agent, signal, 'read'), true)
  register(MEMORY_TOOLS[1], 'Explicit bounded provider search; never ambient context injection.', object({ provider: string, query: string, limit: { type: 'integer', minimum: 1, maximum: 20 }, ...bounds }), (args, agent, signal) => memory(args, agent, signal, 'search'), true)
  register(MEMORY_TOOLS[2], 'Propose a memory write. Only persisted explicitly authorized auto policy writes immediately.', object({ provider: string, key: string, text: string, provenance: string }), (args, agent, signal) => memory(args, agent, signal, 'write'), true)
  // Host projection/approval seam; user configuration stays on native Settings.
  ctx.provide('thaliris', {
    templates: () => import('./policy.mjs').then(module => structuredClone(module.roleTemplates)),
    providers: () => ctx.get('thalirisMemory')?.list() ?? [],
    diagnostics: async (sessionId, signal) => {
      const agent = ctx.agents.get(sessionId)
      await binding(agent)
      const task = await bridge(agent, 'inspect', {}, signal)
      return { task, workspace: await binding(agent), configurationRevision: ctx.get('settings')?.describe({ redactSecrets: true }).find(row => row.ns === ctx.get('configEditor')?.entries().find(entry => entry.fiber?.runtime?.name === name)?.options.id)?.revision ?? null, permissions: { memory: readPolicy(config).memory, roles: readPolicy(config).roles.map(({ id, enabled, tools, memory, context, modelPolicy }) => ({ id, enabled, tools, memory, context, modelPolicy })) },
        providers: ctx.get('thalirisMemory')?.list() ?? [], reservations: await Promise.all(task.state.active_work.map(async value => ({ reservation: JSON.parse(value), native: await nativeObservation(agent, JSON.parse(value), signal, false) }))) }
    },
    approveMemory: async (sessionId, proposalId, signal) => {
      const agent = ctx.agents.get(sessionId)
      const bound = await binding(agent), policy = readPolicy(config)
      const task = await bridge(agent, 'inspect', {}, signal)
      const proposal = task.state.pending_results.map(value => { try { return JSON.parse(value) } catch { return null } }).find(value => value?.proposal_id === proposalId)
      if (!proposal || proposal.workspaceId !== bound.workspaceId || policy.memory.mode === 'disabled' || !policy.memory.providers.includes(proposal.provider) || !policy.memory.controllerWrite.includes(proposal.provider)) throw new Error('THALIRIS_MEMORY_PERMISSION_DENIED')
      const capability = ctx.get('thalirisMemory')
      if (!capability) throw new Error('THALIRIS_MEMORY_CAPABILITY_UNAVAILABLE')
      const value = await capability.invoke(proposal.provider, 'write', { ...proposal, ...bound, signal, maxBytes: 16384 })
      const recorded = await bridge(agent, 'proposal', { observation: JSON.stringify({ approval_id: randomUUID(), proposal_id: proposal.proposal_id, provider: proposal.provider, workspaceId: bound.workspaceId, outcome: 'provider-write-observed', provenance: 'native-client-approval' }) }, signal)
      return { value, recorded: true, ...recorded }
    },
  })
  ctx.effect(() => async () => {
    disposed = true
    for (const cancellation of cancellations) cancellation.abort('Thaliris plugin unloaded')
    await Promise.allSettled([...runs].map(run => run.dispose()))
    await Promise.allSettled([...operations])
    runs.clear(); cancellations.clear()
  })
}
