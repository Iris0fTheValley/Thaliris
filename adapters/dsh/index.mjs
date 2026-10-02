import { createHash } from 'node:crypto'
import { realpathSync } from 'node:fs'
import { isAbsolute } from 'node:path'
import { fileURLToPath } from 'node:url'
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools'

export const name = 'thaliris-dsh'
export const inject = ['agents', 'systemPrompt', 'tools', 'subagents', 'subprocess']
export const TOOL_NAMES = Object.freeze(['thaliris_task_start', 'thaliris_task_inspect', 'thaliris_workstream', 'thaliris_task_close'])
const bridgePath = fileURLToPath(new URL('./core_bridge.py', import.meta.url))
const CONTROLLER_POLICY = `Thaliris Controller contract:
You own task direction, scope, accepted invariants, and semantic completion. Models own semantics; the mechanical layer owns facts. Thaliris records selected intent and mechanical observations; it does not choose roles, judge work, or accept a task for you. For each semantic slice, decide under the selected execution mode whether you may handle the permitted work directly or should delegate. Delegate only when the slice calls for it; if delegating, select the minimum suitable role and send only a bounded handoff; do not send the parent transcript or full working set. An Investigator gathers and compresses facts; an Implementer executes a stable direction; a Focused Implementer handles assigned work that requires sustained reasoning across coupled invariants or nonlocal effects. Native child completion is an observation, not acceptance. Reviewer and other challenge roles are optional when independent review could change a decision, never default gates.`
const CHILD_POLICY = `Thaliris child contract:
Work only within the selected handoff's goal, scope, invariants, acceptance, and context. Treat that handoff as the complete relevant task context: do not infer wider authority, request or reconstruct the parent's transcript or private task records, or expand the assignment. Report a decision-changing unknown instead of widening scope. Native completion is an observation; the Controller decides semantic acceptance.`
const ROLE_POLICY = Object.freeze({
  Investigator: 'As Investigator, gather and verify facts within the selected scope. Return concise findings with exact locations, covered and uncovered scope, unknowns, and contradictions; leave implementation and task decisions to the Controller.',
  Implementer: 'As Implementer, execute the accepted direction for this bounded slice. Make local code decisions, verify the changed behavior, fix ordinary in-scope failures, and synchronize assigned documentation.',
  'Focused Implementer': 'As Focused Implementer, reason through the assigned coupled invariants and nonlocal effects while implementing a coherent candidate. Inspect decision-critical sources directly and return any issue that changes scope, acceptance, or direction to the Controller.',
  Reviewer: 'As Reviewer, independently challenge the candidate with evidence and report material findings; do not implement or decide acceptance.',
  'Reasoning Specialist': 'As Reasoning Specialist, independently challenge framing, assumptions, causal model, and decision basis; report alternatives or missing facts without deciding the task.'
})
const string = { type: 'string' }
const shortString = { type: 'string' }
const object = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required, additionalProperties: false })
const contractSchema = object({ human_instruction: string, boundary: string, invariants: string, acceptance: string, execution_mode: { type: 'string', enum: ['delegated', 'controller-direct', 'single-agent'] } })
const handoffSchema = object({ goal: string, scope: string, invariants: string, acceptance: string, context: string })
const identitySchema = { task_id: shortString, base_revision: { type: 'integer' } }

function validateArguments(parameters, args) {
  const errors = validateJsonSchemaValue(parameters, args)
  if (errors.length) throw new Error(`THALIRIS_INVALID_ARGUMENTS: ${errors.join('; ')}`)
  const visit = (value, key) => {
    if (typeof value === 'string' && (value.length > 16384 || (key !== 'context' && !value.trim()))) throw new Error('THALIRIS_TEXT_BOUND_REQUIRED')
    if (value && typeof value === 'object') for (const [name, item] of Object.entries(value)) visit(item, name)
  }
  visit(args)
  if (args.base_revision !== undefined && (!Number.isSafeInteger(args.base_revision) || args.base_revision < 1)) throw new Error('THALIRIS_REVISION_REQUIRED')
  for (const key of ['workstream', 'role', 'task_id']) if (args[key]?.length > 1024) throw new Error('THALIRIS_LABEL_TOO_LONG')
  if (args.decision?.length > 3500) throw new Error('THALIRIS_DECISION_TOO_LONG')
}

function configuration(raw) {
  if (!raw || typeof raw !== 'object') throw new Error('THALIRIS_CONFIG_REQUIRED')
  const config = structuredClone(raw)
  for (const key of ['root', 'pythonExecutable', 'corePath', 'authorityDirectory']) {
    if (typeof config[key] !== 'string' || !isAbsolute(config[key])) throw new Error(`THALIRIS_ABSOLUTE_CONFIG_REQUIRED: ${key}`)
  }
  config.root = realpathSync(config.root)
  config.pythonExecutable = realpathSync(config.pythonExecutable)
  config.corePath = realpathSync(config.corePath)
  if (!config.roles || typeof config.roles !== 'object' || Array.isArray(config.roles) || !Object.keys(config.roles).length) throw new Error('THALIRIS_ROLE_MAP_REQUIRED')
  for (const [role, route] of Object.entries(config.roles)) {
    if (!/^[A-Za-z][A-Za-z -]{0,63}$/.test(role) || !route || typeof route !== 'object' || !Array.isArray(route.tools)
      || route.tools.some(tool => typeof tool !== 'string' || TOOL_NAMES.includes(tool))) throw new Error('THALIRIS_INVALID_ROLE_ROUTE')
    if (route.agentOptions && (typeof route.agentOptions !== 'object' || Array.isArray(route.agentOptions)
      || Object.keys(route.agentOptions).some(key => !['provider', 'model', 'reasoningEffort', 'maxTokens'].includes(key)))) throw new Error('THALIRIS_INVALID_AGENT_OPTIONS')
    if (route.persona !== undefined && typeof route.persona !== 'string') throw new Error('THALIRIS_INVALID_PERSONA')
  }
  config.subagentProvider ??= 'spawn'
  config.bridgeTimeoutMs ??= 30000
  if (typeof config.subagentProvider !== 'string' || !Number.isSafeInteger(config.bridgeTimeoutMs) || config.bridgeTimeoutMs <= 0 || config.bridgeTimeoutMs > 300000) throw new Error('THALIRIS_INVALID_CONFIG')
  return config
}

/** Cordis owns registrations; DSH owns Agent, child and process lifecycle. */
export function apply(ctx, raw) {
  const config = configuration(raw)
  let controller
  let disposed = false
  let tail = Promise.resolve()
  const operations = new Set()
  const cancellations = new Set()
  const runs = new Set()

  function isNativeRoot(agent) {
    return !!agent
      && ctx.agents.get(agent.id) === agent
      && ctx.agents.roots().includes(agent)
      && agent.session.header.parentSession === undefined
      && (agent.session.header.delegationDepth ?? 0) === 0
      && agent.session.header.origin !== 'subagent'
      && !!agent.session.header.cwd
      && realpathSync(agent.session.header.cwd) === config.root
  }

  const disposePrompt = ctx.systemPrompt.section({
    name: 'thaliris:controller-contract',
    order: ctx.systemPrompt.getSectionOrder('TEAM_POLICY'),
    text: ({ agent }) => isNativeRoot(agent) ? CONTROLLER_POLICY : '',
  })

  function authorize(exec) {
    const agent = exec.agent
    if (disposed || !isNativeRoot(agent)) throw new Error('THALIRIS_NATIVE_ROOT_REQUIRED')
    if (controller && controller !== agent) throw new Error('THALIRIS_CONTROLLER_MISMATCH')
    return agent
  }

  async function bridge(agent, operation, args, signal) {
    signal.throwIfAborted()
    const deadline = new AbortController()
    const timer = setTimeout(() => deadline.abort('Thaliris bridge deadline exceeded'), config.bridgeTimeoutMs)
    timer.unref()
    const processSignal = AbortSignal.any([signal, deadline.signal])
    let command
    try {
      command = ctx.subprocess.spawn({
        argv: [config.pythonExecutable, '-I', bridgePath], cwd: config.root, graceMs: 1000,
        signal: processSignal,
        stdio: { stdin: { data: JSON.stringify({ protocol: 1, core_path: config.corePath, root: config.root,
          authority_directory: config.authorityDirectory, native_controller_id: agent.id, operation, arguments: args }) },
        stdout: { maxBytes: 1048576 }, stderr: { maxBytes: 8192 } },
      })
      const outcome = await command.done
      const stdout = command.collected.stdout.readFrom(0)
      if (stdout.lossy) throw new Error('THALIRIS_BRIDGE_RESPONSE_TOO_LARGE')
      const response = JSON.parse(stdout.text)
      if (response.protocol !== 1 || response.ok !== true || outcome.exitCode !== 0) throw new Error(response.error ?? 'THALIRIS_BRIDGE_FAILED')
      processSignal.throwIfAborted()
      return response.result
    } finally {
      clearTimeout(timer)
      if (command) {
        command.terminate()
        await command.waitForExit()
      }
    }
  }

  function tool(toolName, description, parameters, execute) {
    ctx.tools.register({ name: toolName, description, parameters,
      output: { schema: { type: 'object', additionalProperties: true }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
      async execute(args, exec) {
        // Also checked in the body: schema visibility alone is not authority.
        const agent = authorize(exec)
        validateArguments(parameters, args)
        const cancellation = new AbortController()
        const signal = AbortSignal.any([exec.signal, cancellation.signal])
        cancellations.add(cancellation)
        const operation = tail.then(async () => {
          authorize(exec)
          signal.throwIfAborted()
          const result = await execute(args, agent, signal)
          controller = agent
          return result
        })
        tail = operation.catch(() => {})
        operations.add(operation)
        try { return await operation } finally { operations.delete(operation); cancellations.delete(cancellation) }
      },
    })
  }

  tool(TOOL_NAMES[0], 'Controller explicitly selects human intent and starts the Core task. No inferred consent.', object({ goal: string, contract: contractSchema }),
    (args, agent, signal) => bridge(agent, 'start', args, signal))
  tool(TOOL_NAMES[1], 'Controller explicitly retrieves the current Core task and selected contract.', object({}),
    (_args, agent, signal) => bridge(agent, 'inspect', {}, signal))
  tool(TOOL_NAMES[2], 'Controller selects one bounded Workstream, role and context. Starts a fresh native child and returns observed native status. Controller interprets the result.',
    object({ ...identitySchema, workstream: shortString, role: shortString, handoff: handoffSchema }), async (args, agent, signal) => {
      const route = Object.hasOwn(config.roles, args.role) ? config.roles[args.role] : undefined
      if (!route) throw new Error('THALIRIS_ROLE_NOT_CONFIGURED')
      const provider = ctx.subagents.getProvider(config.subagentProvider)
      if (!provider || provider.inheritsParentContext !== false) throw new Error('THALIRIS_FRESH_PROVIDER_REQUIRED')
      const inspected = await bridge(agent, 'inspect', {}, signal)
      if (inspected.contract.execution_mode !== 'delegated') throw new Error('THALIRIS_DELEGATED_INTENT_REQUIRED')
      const prompt = JSON.stringify({ workstream: args.workstream, role: args.role, ...args.handoff })
      const persona = [route.persona, CHILD_POLICY, ROLE_POLICY[args.role]].filter(Boolean).join('\n\n')
      const selected = { workstream: args.workstream, role: args.role, handoff_sha256: createHash('sha256').update(prompt).digest('hex') }
      const begun = await bridge(agent, 'begin', { task_id: args.task_id, base_revision: args.base_revision, observation: JSON.stringify(selected) }, signal)
      let run
      try {
        run = await ctx.subagents.start(config.subagentProvider, {
          parent: agent, signal, label: args.workstream, prompt: [{ type: 'text', text: prompt }], maxDepth: 1,
          toolFilter: { allow: route.tools, deny: TOOL_NAMES },
          ...(route.agentOptions === undefined ? {} : { agentOptions: route.agentOptions }),
          persona,
        })
        runs.add(run)
        if (!run.localAgent || run.localAgent.id !== run.id || run.localAgent.session.header.parentSession !== agent.id
          || run.localAgent.session.header.isSeeded !== false) throw new Error('THALIRIS_NATIVE_CHILD_IDENTITY_REQUIRED')
        const result = await run.result
        // Prose remains in the native result, never supplies identity or status.
        const observed = { ...selected, child_id: run.id, stop_reason: result.stopReason }
        const ack = await bridge(agent, 'finish', { task_id: args.task_id, base_revision: begun.revision, observation: JSON.stringify(observed) }, signal)
        const observation = { ...ack, child_id: run.id, stop_reason: result.stopReason, native_completed: result.stopReason === 'completed', output: result.output,
          ...(result.diagnostic === undefined ? {} : { diagnostic: result.diagnostic }) }
        if (result.stopReason !== 'completed') throw new Error('THALIRIS_NATIVE_CHILD_FAILED: ' + JSON.stringify(observation))
        return observation
      } finally {
        if (run) { await run.dispose(); runs.delete(run) }
      }
    })
  tool(TOOL_NAMES[3], 'Controller explicitly decides that the task is complete. Native child completion does not close it.',
    object({ ...identitySchema, decision: string }),
    (args, agent, signal) => bridge(agent, 'close', args, signal))

  ctx.effect(() => async () => {
    disposed = true
    for (const cancellation of cancellations) cancellation.abort('Thaliris plugin unloaded')
    await Promise.allSettled([...runs].map(run => run.dispose()))
    await Promise.allSettled([...operations])
    runs.clear()
    cancellations.clear()
    controller = undefined
    disposePrompt()
    // Durable ACTIVE/DONE ledgers and native parent sessions are never deleted.
  }, 'thaliris owned operations')
}
