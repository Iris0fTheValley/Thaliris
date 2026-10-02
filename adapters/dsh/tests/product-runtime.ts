import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdir, mkdtemp, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { boot, initProfile, readProfilePatches } from '@deepseek-ai/dsh-app-boot'
import ConfigEditor from '@deepseek-ai/dsh-config-editor'
import Settings from '@deepseek-ai/dsh-settings'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import Subagents from '@deepseek-ai/dsh-subagent'
import * as Spawn from '@deepseek-ai/dsh-subagent-spawn-in-process'
import LocalSubprocess from '@deepseek-ai/dsh-subprocess-local'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import Persistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import WorkspaceRegistry from '@deepseek-ai/dsh-workspace'
import { SessionId } from '@deepseek-ai/dsh-session'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import * as Plugin from '../index.mjs'
import Api from '../api.mjs'
import { remoteContribution } from '../remote.mjs'
import * as ClientGateway from '@deepseek-ai/dsh-api-gateway/client'
import Registry from '@deepseek-ai/dsh-typert-registry'
import Gateway from '@deepseek-ai/dsh-api-gateway'
import Memory from '../components/memory/index.mjs'
import * as LocalMemory from '../components/memory-local/index.mjs'
const upstream = process.env.DSH_SOURCE!
const { MockAdapter, textResponse, toolCallResponse } = await import(pathToFileURL(join(upstream, 'packages/core/agent-loop/tests/mock-adapter.ts')).href)
const corePath = fileURLToPath(new URL('../../../src', import.meta.url))
const bridgePath = fileURLToPath(new URL('../core_bridge.py', import.meta.url))
const script: any[] = []
const signal = () => new AbortController().signal
const contract = { human_instruction: 'Product runtime fixture', boundary: 'Temporary fixtures only', invariants: 'Native durable identity, optional memory, editable policy', acceptance: 'Controller decides', execution_mode: 'delegated' }
const role = { id: 'editable', name: 'My role', description: 'Fully editable', enabled: true, prompt: 'EXACT_EDITED_PROMPT', tools: [], modelPolicy: { mode: 'allowed', routes: [{ provider: 'mock', model: 'child' }] }, memory: { read: [], write: [] }, context: { handoff: true, memory: false } }
const handoff = { goal: 'Fixture', scope: 'Text only', invariants: 'No ambient input', acceptance: 'Controller assesses', context: 'BOUNDED_SELECTION' }
async function harness(home: string, initialize: boolean, resumeRoot = true) {
  const dir = join(home, 'profiles', 'product'), workspace = join(home, 'repo'), secondRoot = join(home, 'second')
  if (initialize) {
    await mkdir(workspace); await mkdir(secondRoot)
    execFileSync('git', ['init', '-q', workspace]); execFileSync('git', ['init', '-q', secondRoot])
    initProfile(dir, ['fixture-bundle'])
    await mkdir(join(dir, 'node_modules', 'fixture-bundle'), { recursive: true })
    await writeFile(join(home, 'package.json'), JSON.stringify({ name: 'test-installation' }))
    await writeFile(join(dir, 'cordis.yml'), '[]\n')
    await writeFile(join(dir, 'node_modules', 'fixture-bundle', 'package.json'), JSON.stringify({ name: 'fixture-bundle', version: '1.0.0', dsh: { bundle: { patch: 'cordis.patch.yml' } } }))
  }
  const profile = { name: 'product', startedBundles: ['fixture-bundle'], dir, patchPath: join(dir, 'cordis.patch.yml'), installAnchor: join(home, 'package.json'), cwd: home, home, overlays: [], telemetryDisabledEnv: undefined }
  const mock = new MockAdapter(script)
  const patches = initialize ? [] : readProfilePatches('product', profile as any)
  const ctx = await boot('product', join(dir, 'cordis.yml'), patches, async ctx => {
    ctx.provide('profileContext', profile as any)
    await mountAgentLoopTestDependencies(ctx)
    await ctx.plugin(Persistence, { root: join(home, 'sessions'), compression: 'none' })
    await ctx.plugin(Storage); await ctx.plugin(StorageJson, { root: join(home, 'storage') }); await ctx.plugin(StorageDomain, { backend: 'json' })
    await ctx.plugin(WorkspaceRegistry)
    const first = await ctx.workspaceRegistry.create(workspace), second = await ctx.workspaceRegistry.create(secondRoot)
    await ctx.plugin(AgentLoop, { agents: [] }); await ctx.plugin(Subagents); await ctx.plugin(Spawn, { providerName: 'spawn' }); await ctx.plugin(LocalSubprocess)
    ctx.llm.registerAdapter(['mock'], mock)
    Object.assign(ctx.loader.builtins, { editor: ConfigEditor, settings: Settings, thaliris: Plugin })
    if (initialize) {
      await writeFile(join(dir, 'node_modules', 'fixture-bundle', 'cordis.patch.yml'), JSON.stringify([{ insert: [
        { id: 'editor', name: 'cordis:editor' }, { id: 'settings', name: 'cordis:settings' },
        { id: 'thaliris', name: 'cordis:thaliris', config: { pythonExecutable: process.env.THALIRIS_TEST_PYTHON, corePath, authorityDirectory: join(home, 'authority'), policy: {
          workspaces: [{ workspaceId: first.id, root: workspace, enabled: true }, { workspaceId: second.id, root: secondRoot, enabled: true }], roles: [role],
        } } },
      ] }]))
      patches.push(...readProfilePatches('product', profile as any))
    }
  })
  await ctx.plugin(Registry); await ctx.plugin(Gateway); await ctx.plugin(Api)
  const parent = initialize ? await ctx.agentLoop.create(SessionId('persistent-controller'), { provider: 'mock', model: 'parent' }, { cwd: workspace })
    : resumeRoot ? (await ctx.agents.resume({ resumeSessionId: SessionId('persistent-controller'), agentOptions: { provider: 'mock', model: 'parent' } })).agent : undefined
  await ctx.sessionPersistence.flush()
  let call = 0
  const execute = (name: string, args: any, agent = parent) => ctx.tools.execute({ callId: ToolCallId(`product-${++call}`), name, arguments: args, agent, signal: signal() })
  const view = () => ctx.settings.describe().find(row => row.ns === 'thaliris')!
  const edit = async (ops: any[], expected = view().revision) => ctx.settings.mutate('thaliris', ops, expected)
  const inspect = async () => { const value: any = await execute('thaliris_task_inspect', {}); assert.equal(value.isError, false); return value.value }
  return { ctx, parent, execute, edit, view, inspect, mock, workspace, secondRoot }
}
function bridge(home: string, operation: string, arguments_: any) {
  return JSON.parse(execFileSync(process.env.THALIRIS_TEST_PYTHON!, ['-I', bridgePath], { input: JSON.stringify({ protocol: 1, core_path: corePath, root: join(home, 'repo'), authority_directory: join(home, 'authority'), native_controller_id: 'persistent-controller', native_workspace_id: arguments_.workspaceId, operation, arguments: arguments_.args }), encoding: 'utf8' }))
}
async function initialize(home: string) {
  const h = await harness(home, true)
  try {
    const start: any = await h.execute('thaliris_task_start', { goal: 'Product fixture', contract }); assert.equal(start.isError, false, JSON.stringify(start))
    const unbound = await h.ctx.agentLoop.create(SessionId('unbound-controller'), { provider: 'mock', model: 'parent' }, { cwd: h.secondRoot })
    await h.ctx.sessionPersistence.flush()
    const originalWorkspaces = structuredClone(h.view().value.policy.workspaces)
    const staleRoot = join(h.workspace, 'removed-unrelated-workspace')
    await h.edit([{ op: 'set', path: ['policy', 'workspaces'], value: [
      originalWorkspaces[0],
      { workspaceId: 'removed-native-workspace', root: staleRoot, enabled: true },
    ] }])
    const promptSection = async (agent: any) => (await h.ctx.systemPrompt.assemble({ agent })).sections.find((section: any) => section.name === 'thaliris:controller-contract')?.text ?? ''
    assert.match(await promptSection(h.parent), /Thaliris Controller contract:/, 'a stale unrelated binding does not break the configured root prompt')
    assert.equal(await promptSection(unbound), '', 'an unbound native root receives no Thaliris prompt even with an unrelated stale binding')
    await h.edit([{ op: 'set', path: ['policy', 'workspaces'], value: originalWorkspaces }])
    const client = new Context()
    await client.plugin(Registry)
    client.provide('connection', { registerGenerationSource: () => () => {}, start: () => ({ stop() {} }), rpc: {
      open: () => (async function* () {})(),
      call: async (_channel: string, endpoint: string, payload: any) => {
        const [namespace, method] = endpoint.split('/')
        try { return { ok: true, value: await h.ctx.typertGateway.invoke({ namespace: namespace!, method: method!, args: payload.args }) } }
        catch (error: any) { return { ok: false, error: { code: 'gateway/internal', message: error.message, details: {} } } }
      },
    } } as any)
    await client.plugin(ClientGateway)
    const unmount = await client.remote.$mount(remoteContribution)
    const clientTemplates: any = await (client.remote as any).thaliris.templates(); assert.equal(clientTemplates.ok, true); assert.ok(clientTemplates.value.length)
    const clientTools: any = await (client.remote as any).thaliris.toolCatalog(); assert.equal(clientTools.ok, true)
    assert.ok(clientTools.value.some((tool: any) => tool.name === 'thaliris_task_start'))
    assert.deepEqual(Object.keys(clientTools.value[0] ?? {}).sort(), ['description', 'name'])
    const clientDiagnostics: any = await (client.remote as any).thaliris.diagnostics(h.parent.id); assert.equal(clientDiagnostics.ok, true); assert.equal(clientDiagnostics.value.task.state.status, 'ACTIVE')
    await unmount(); await client.fiber.dispose()
    const templates: any = await h.ctx.typertGateway.invoke({ namespace: 'thaliris', method: 'templates', args: {} }); assert.ok(templates.some((value: any) => value.id === 'curator'))
    const diagnostics: any = await h.ctx.typertGateway.invoke({ namespace: 'thaliris', method: 'diagnostics', args: { sessionId: h.parent.id } }); assert.equal(diagnostics.task.state.status, 'ACTIVE'); assert.equal(typeof diagnostics.configurationRevision, 'number')
    const bytes = await readFile(join(h.workspace, '.context/state.json'))
    const rev = h.view().revision
    await h.edit([{ op: 'set', path: ['policy', 'controllerPrompt'], value: 'VISIBLE_EDITED_CONTROLLER' }], rev)
    await assert.rejects(h.edit([{ op: 'set', path: ['policy', 'roles'], value: [] }], rev), /changed since/)
    assert.deepEqual(await readFile(join(h.workspace, '.context/state.json')), bytes, 'Settings edits never rewrite task intent')
    await h.edit([{ op: 'set', path: ['policy', 'roles'], value: [] }])
    assert.deepEqual((h.view().value as any).policy.roles, [])
    let task = await h.inspect()
    assert.equal((await h.execute('thaliris_workstream', { task_id: task.state.task_id, base_revision: task.state.revision, role: role.id, workstream: 'removed', handoff })).isError, true)
    const unrelatedInvalid = { ...role, id: 'disabled-fixed-role', enabled: false, modelPolicy: { mode: 'fixed', routes: [] } }
    const selectedInvalid = { ...role, id: 'invalid-fixed-role', modelPolicy: { mode: 'fixed', routes: [] } }
    await h.edit([{ op: 'set', path: ['policy', 'roles'], value: [role, unrelatedInvalid, selectedInvalid] }])
    const denied: any = await h.execute('thaliris_workstream', { task_id: task.state.task_id, base_revision: task.state.revision, role: role.id, workstream: 'denied', handoff, route: { provider: 'mock', model: 'other' } })
    assert.equal(denied.isError, true); assert.match(JSON.stringify(denied), /MODEL_ROUTE_NOT_ALLOWED/)
    const invalidRoute: any = await h.execute('thaliris_workstream', { task_id: task.state.task_id, base_revision: task.state.revision, role: selectedInvalid.id, workstream: 'invalid-selected-role', handoff })
    assert.equal(invalidRoute.isError, true); assert.match(JSON.stringify(invalidRoute), /FIXED_ROUTE_REQUIRED/)
    script.push((request: any) => { assert.ok(JSON.stringify(request).includes('EXACT_EDITED_PROMPT')); assert.ok(!JSON.stringify(request).includes('Thaliris child contract:')); return textResponse('editable role complete') })
    const routed: any = await h.execute('thaliris_workstream', { task_id: task.state.task_id, base_revision: task.state.revision, role: role.id, workstream: 'editable', handoff, route: { provider: 'mock', model: 'child' } }); assert.equal(routed.isError, false, JSON.stringify(routed))
    await h.edit([{ op: 'set', path: ['policy', 'roles'], value: [] }])
    // Empty set persists; no hidden regeneration.
    const second = await h.ctx.agentLoop.create(SessionId('second-controller'), { provider: 'mock', model: 'parent' }, { cwd: h.secondRoot })
    await h.ctx.sessionPersistence.flush()
    assert.equal((await h.execute('thaliris_task_start', { goal: 'Isolated second workspace', contract }, second)).isError, false)
    assert.notEqual((await h.execute('thaliris_task_inspect', {}, second) as any).value.state.task_id, task.state.task_id)
    assert.equal((await h.execute('thaliris_task_close', { task_id: task.state.task_id, base_revision: 1, decision: 'Cross-workspace attack' }, second)).isError, true)
    // Native, independently disposable provider plugins; remote-style fixture is injected at the same seam.
    const memoryFiber = await h.ctx.plugin(Memory)
    const localFiber = await h.ctx.plugin(LocalMemory)
    let writes = 0
    const externalFiber = await h.ctx.plugin({ inject: ['thalirisMemory'], apply(ctx: Context) { (ctx as any).thalirisMemory.register(ctx, { id: 'external', name: 'External async fixture', async read(request: any) { return { text: request.key === 'unicode' ? '😀'.repeat(10) : 'external' } }, async search() { return [{ key: 'remote', text: 'external' }] }, async write() { writes++; return { stored: true } } }) } })
    await assert.rejects((h.ctx as any).thalirisMemory.invoke('external', 'read', { key: 'unicode', signal: signal(), maxBytes: 31 }), /THALIRIS_MEMORY_RESULT_BOUND_EXCEEDED/)
    await h.edit([{ op: 'set', path: ['policy', 'memory'], value: { mode: 'manual', autoAuthorized: false, providers: ['thaliris-local', 'external'], controllerRead: ['thaliris-local', 'external'], controllerWrite: ['thaliris-local', 'external'] } }])
    assert.equal((await h.execute('thaliris_memory_read', { provider: 'external', key: 'x', maxBytes: 64 })).isError, false)
    assert.equal((await h.execute('thaliris_memory_read', { provider: 'forbidden', key: 'x', maxBytes: 64 })).isError, true)
    assert.equal((await h.execute('thaliris_memory_search', { provider: 'external', query: 'x', limit: 1, maxBytes: 1 })).isError, true)
    const proposed: any = await h.execute('thaliris_memory_propose', { provider: 'external', key: 'x', text: 'selected', provenance: 'user-selected fixture' }); assert.equal(proposed.isError, false); assert.equal(writes, 0)
    await h.ctx.typertGateway.invoke({ namespace: 'thaliris', method: 'approveMemory', args: { sessionId: h.parent.id, proposalId: proposed.value.proposal_id } }); assert.equal(writes, 1)
    await h.edit([{ op: 'set', path: ['policy', 'memory', 'mode'], value: 'suggest-review' }])
    const suggestion: any = await h.execute('thaliris_memory_propose', { provider: 'thaliris-local', key: 'local', text: 'stored after review', provenance: 'fixture' }); assert.equal(suggestion.isError, false)
    await (h.ctx as any).thaliris.approveMemory(h.parent.id, suggestion.value.proposal_id, signal())
    assert.equal((await h.execute('thaliris_memory_read', { provider: 'thaliris-local', key: 'local', maxBytes: 512 }) as any).value.value.text, 'stored after review')
    // Auto remains refused at execution until both persisted user policy fields opt in.
    await h.edit([{ op: 'set', path: ['policy', 'memory', 'mode'], value: 'auto' }])
    assert.equal((await h.execute('thaliris_memory_propose', { provider: 'external', key: 'x', text: 'no consent', provenance: 'fixture' })).isError, true)
    await h.edit([{ op: 'set', path: ['policy', 'memory', 'autoAuthorized'], value: true }])
    assert.equal((await h.execute('thaliris_memory_propose', { provider: 'external', key: 'x', text: 'consented', provenance: 'fixture' })).isError, false); assert.equal(writes, 2)
    await h.edit([{ op: 'set', path: ['policy', 'memory', 'mode'], value: 'suggest-review' },
      { op: 'set', path: ['policy', 'roles'], value: [{ ...role, tools: [...Plugin.MEMORY_TOOLS], memory: { read: ['external'], write: [] }, context: { handoff: true, memory: true } }] }])
    script.push((options: any) => { assert.match(JSON.stringify(options.messages), /memory_context/); return toolCallResponse('read', 'thaliris_memory_read', { provider: 'external', key: 'x', maxBytes: 64 }) },
      toolCallResponse('denied-write', 'thaliris_memory_propose', { provider: 'external', key: 'x', text: 'denied', provenance: 'fixture' }),
      (options: any) => { assert.match(JSON.stringify(options.messages), /MEMORY_PERMISSION_DENIED/); return textResponse('child permission fixture') })
    task = await h.inspect()
    const childMemory: any = await h.execute('thaliris_workstream', { task_id: task.state.task_id, base_revision: task.state.revision, role: role.id, workstream: 'memory-grants', handoff, memoryContext: [{ provider: 'external', operation: 'read', key: 'x', maxBytes: 64 }], route: { provider: 'mock', model: 'child' } })
    assert.equal(childMemory.isError, false, JSON.stringify(childMemory))
    await h.edit([{ op: 'set', path: ['policy', 'roles', '0', 'memory', 'write'], value: ['external'] }])
    script.push(toolCallResponse('suggest', 'thaliris_memory_propose', { provider: 'external', key: 'x', text: 'child suggestion', provenance: 'selected child' }),
      (options: any) => { assert.match(JSON.stringify(options.messages), /proposal_id/); return textResponse('suggestion proposed') })
    task = await h.inspect()
    assert.equal((await h.execute('thaliris_workstream', { task_id: task.state.task_id, base_revision: task.state.revision, role: role.id, workstream: 'memory-proposal', handoff, route: { provider: 'mock', model: 'child' } })).isError, false)
    assert.equal(writes, 2, 'Curator/child proposal cannot enable automatic writes')
    await h.edit([{ op: 'set', path: ['policy', 'roles'], value: [] }])
    await localFiber.dispose(); assert.equal((h.ctx as any).thaliris.providers().length, 1)
    await externalFiber.dispose(); await memoryFiber.dispose()
    assert.equal((h.ctx as any).thaliris.providers().length, 0)
    await h.edit([{ op: 'set', path: ['policy', 'roles'], value: [role] }])
    task = await h.inspect(); script.push(textResponse('routing after memory uninstall'))
    assert.equal((await h.execute('thaliris_workstream', { task_id: task.state.task_id, base_revision: task.state.revision, role: role.id, workstream: 'no-memory', handoff, route: { provider: 'mock', model: 'child' } })).isError, false)
    await h.edit([{ op: 'set', path: ['policy', 'roles'], value: [] }])
    await h.edit([{ op: 'set', path: ['policy', 'memory', 'mode'], value: 'disabled' }])
    assert.equal((await h.execute('thaliris_memory_read', { provider: 'external', key: 'x', maxBytes: 64 })).isError, true)
    assert.equal((await h.execute('thaliris_task_close', { task_id: (await h.execute('thaliris_task_inspect', {}, second) as any).value.state.task_id, base_revision: 1, decision: 'Native task closes with memory absent' }, second)).isError, false)
    // Crash window: Core has reservation, native catalog has exact child, bind/finish never ran.
    task = await h.inspect()
    const reservation = { workstream: 'crash-window', role: 'fixture', handoff_sha256: 'fixture-digest', correlation: 'thaliris:unique-crash-window' }
    const workspaceId = (await h.ctx.workspaceRegistry.resolveByPath(h.workspace))!.id
    const begun = bridge(home, 'begin', { workspaceId, args: { task_id: task.state.task_id, base_revision: task.state.revision, observation: JSON.stringify(reservation) } }); assert.equal(begun.ok, true)
    script.push(textResponse('native completed before bridge acknowledgement'))
    const run = await h.ctx.subagents.start('spawn', { parent: h.parent, signal: signal(), label: reservation.correlation, prompt: [{ type: 'text', text: 'Selected crash fixture' }], maxDepth: 1, toolFilter: { allow: [], deny: Plugin.TOOL_NAMES }, persona: 'Fixture' })
    assert.equal((await run.result).stopReason, 'completed')
    await h.ctx.sessionPersistence.flush(); await run.dispose()
    const check: any = await h.execute('thaliris_reconcile', { task_id: task.state.task_id, base_revision: begun.result.revision, action: 'check' }); assert.equal(check.value.outcome, 'completed'); assert.equal(check.value.released, false)
    console.log('PASS native Settings revision/prompt/deletion/model grants; multiple workspaces; optional local/external providers manual/review/auto opt-in/removal; catalog crash fixture')
  } finally { await h.ctx.fiber.dispose() }
}
async function restart(home: string) {
  const unloaded = await harness(home, false, false)
  try {
    assert.equal(unloaded.ctx.agents.get(SessionId('persistent-controller')), undefined, 'fixture begins with no live Agent for the persisted root Session')
    const diagnostics: any = await unloaded.ctx.typertGateway.invoke({ namespace: 'thaliris', method: 'diagnostics', args: { sessionId: 'persistent-controller' } })
    assert.equal(diagnostics.task.state.status, 'ACTIVE', 'native diagnostics resumes the exact persisted root Agent and reads its current Core task')
    assert.equal(diagnostics.workspace.workspaceId, (await unloaded.ctx.workspaceRegistry.resolveByPath(unloaded.workspace))!.id)
    assert.equal(unloaded.ctx.agents.get(SessionId('persistent-controller')), undefined, 'one-shot diagnostics disposes only the Agent handle it resumed')
    console.log('PASS Gateway diagnostics resumes and validates a persisted configured root Session, then disposes its owned Agent handle')
  } finally { await unloaded.ctx.fiber.dispose() }
  const h = await harness(home, false)
  try {
    assert.deepEqual((h.view().value as any).policy.roles, [], 'deleted roles stay deleted after fresh process')
    assert.equal((h.view().value as any).policy.controllerPrompt, 'VISIBLE_EDITED_CONTROLLER')
    const task = await h.inspect()
    assert.equal(task.state.active_work.length, 1)
    const rival = await h.ctx.agentLoop.create(SessionId('unrelated-root'), { provider: 'mock', model: 'parent' }, { cwd: h.workspace }); await h.ctx.sessionPersistence.flush()
    assert.equal((await h.execute('thaliris_task_inspect', {}, rival)).isError, true)
    await h.edit([{ op: 'set', path: ['policy', 'roles'], value: [
      { ...role, id: 'disabled-fixed-role', enabled: false, modelPolicy: { mode: 'fixed', routes: [] } },
    ] }])
    const lifecycle = await h.inspect()
    assert.equal(lifecycle.state.active_work.length, 1, 'disabled invalid role does not block lifecycle inspection')
    const reconciled: any = await h.execute('thaliris_reconcile', { task_id: lifecycle.state.task_id, base_revision: lifecycle.state.revision, action: 'reconcile' })
    assert.equal(reconciled.isError, false, JSON.stringify(reconciled)); assert.equal(reconciled.value.native_completed, true)
    const state = (await h.inspect()).state
    assert.equal(state.active_work.length, 0); assert.ok(state.pending_results.some((value: string) => value.includes('Archived reservation:')))
    assert.equal((await h.execute('thaliris_task_close', { task_id: state.task_id, base_revision: state.revision, decision: 'Controller accepted native evidence after restart with memory removed' })).isError, false)
    console.log('PASS fresh process/runtime persisted native Workspace + same Session/new Agent Core continuation; rival denial; durable completed reconciliation; close without memory')
  } finally { await h.ctx.fiber.dispose() }
}
const phase = process.argv[2], home = process.argv[3]
if (phase === 'init') await initialize(home!)
else if (phase === 'restart') await restart(home!)
else {
  const directory = await mkdtemp(join(tmpdir(), 'thaliris-product-'))
  try {
    for (const stage of ['init', 'restart']) {
      const child = spawnSync(process.execPath, [...process.execArgv, fileURLToPath(import.meta.url), stage, directory], { stdio: 'inherit', env: process.env, timeout: 120000 })
      assert.equal(child.status, 0, `${stage}: ${child.error ?? ''}`)
    }
  } finally { await rm(directory, { recursive: true, force: true }) }
}
