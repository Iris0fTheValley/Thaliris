// @vitest-environment jsdom
import { useSyncExternalStore } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import { SlotRegistry } from '@deepseek-ai/dsh-client-ui-renderer/client'
import { LocaleRuntime } from '@deepseek-ai/dsh-client-locale/client'
import * as Gateway from '@deepseek-ai/dsh-api-gateway/client'
import * as TypertRegistry from '@deepseek-ai/dsh-typert-registry/client'
import type { ConfigForm, ConfigFormSnapshot } from '@deepseek-ai/dsh-client-ui-settings/client'
import type { ModelCatalog } from '@deepseek-ai/dsh-api-remotes/client'
import type { SessionListState } from '@deepseek-ai/dsh-api-session-controller/client'
import type { WorkspaceSnapshot } from '@deepseek-ai/dsh-api-workspace-controller/client'
import type { RoleRecord, UserPolicy } from '../remote'
import { NS, en } from '../client/locales.ts'
import { PolicyEditorController, type ThalirisSettings } from '../client/policy-controller.ts'
import type { NativeProjectionState } from '../client/native-controller.ts'
import { NativeProjectionController } from '../client/native-controller.ts'
import { ThalirisPage, type ThalirisPageFace } from '../client/ThalirisPage.tsx'
import { remoteContribution } from '../remote.mjs'

const role = (id: string): RoleRecord => ({
  id, name: id, description: '', prompt: `full prompt for ${id}`, enabled: true, tools: [],
  modelPolicy: { mode: 'inherit', routes: [] }, memory: { read: [], write: [] },
  context: { handoff: true, memory: false },
})

const policy = (): UserPolicy => ({
  controllerPrompt: 'Visible Controller instructions', workspaces: [], roles: [role('implementer')],
  memory: { mode: 'disabled', autoAuthorized: false, providers: [], controllerRead: [], controllerWrite: [] },
})

function createForm(value = policy(), writable = true) {
  let snapshot: ConfigFormSnapshot<ThalirisSettings> = {
    status: 'ready', value: { policy: structuredClone(value) }, base: {}, user: {}, revision: 8,
    writable, mode: 'host',
  }
  const listeners = new Set<() => void>()
  const publish = (next: ConfigFormSnapshot<ThalirisSettings>): void => {
    snapshot = next
    for (const listener of [...listeners]) listener()
  }
  const mutate = vi.fn(async (ops: readonly { op: 'set' | 'unset'; path: readonly string[]; value?: unknown }[], expected?: number) => {
    if (!writable || expected !== snapshot.revision) return false
    const next = structuredClone(snapshot.value!)
    for (const op of ops) {
      if (op.path[0] !== 'policy') throw new Error(`unexpected path ${op.path.join('.')}`)
      const field = op.path[1] as keyof UserPolicy
      if (op.op === 'set') next.policy[field] = structuredClone(op.value) as never
    }
    publish({ ...snapshot, value: next, revision: snapshot.revision! + 1 })
    return true
  })
  const form: ConfigForm<ThalirisSettings> = {
    getSnapshot: () => snapshot,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener) } },
    mutate: mutate as ConfigForm<ThalirisSettings>['mutate'],
    set: async () => false,
    unset: async () => false,
  }
  return { form, mutate, publish, getSnapshot: () => snapshot }
}

const modelCatalog = {
  default: { provider: 'alpha', model: 'fast' }, routableProviders: ['alpha', 'beta'], failures: [],
  groups: [
    { id: 'alpha', name: 'Alpha', models: [{ id: 'fast', name: 'Fast', reasoning: {
      efforts: [{ id: 'high', name: 'High' }], defaultEffort: 'high',
    } }] },
    { id: 'beta', name: 'Beta', models: [{ id: 'accurate', name: 'Accurate' }] },
  ],
} satisfies ModelCatalog

const sessions = {
  ids: ['root-session', 'child-session'],
  byId: {
    'root-session': { id: 'root-session', displayTitle: 'Root workspace', parentId: undefined, origin: undefined },
    'child-session': { id: 'child-session', displayTitle: 'Observed child', parentId: 'root-session', origin: 'subagent' },
  }, phase: 'ready', projectionsBySession: {},
} as unknown as SessionListState

const workspaces = {
  items: [{ workspaceId: 'workspace-1', path: 'C:/repo', title: 'Repo', sessionIds: [], createdAt: '', updatedAt: '' }],
  archivedSessionIds: [], pinnedSessionIds: [], state: 'idle', phase: 'ready', error: null,
} satisfies WorkspaceSnapshot

const diagnostics = {
  task: { contract: { execution_mode: 'delegated' }, state: {
    task_id: 'task-1', revision: 4,
    pending_results: [JSON.stringify({ proposal_id: 'proposal-1', provider: 'provider-one', key: 'decision', text: 'proposed note', provenance: { source: 'test' } })],
  } },
  workspace: { workspaceId: 'workspace-1', root: 'C:/repo' }, configurationRevision: 8,
  permissions: { memory: { mode: 'manual', providers: ['provider-one'], controllerRead: [], controllerWrite: ['provider-one'] }, roles: [] },
  providers: [{ id: 'provider-one', name: 'Provider One' }],
  reservations: [{ reservation: { workstream: 'test-slice', correlation: 'thaliris:test' }, native: {
    child_id: 'child-session', outcome: 'completed', terminal_seq: 19, provenance: 'native-session-turn/end',
  } }],
}

function nativeState(): NativeProjectionState {
  return {
    modelCatalog, modelStatus: 'ready' as const,
    providers: [{ id: 'provider-one', name: 'Provider One' }], providerStatus: 'ready' as const,
    tools: [{ name: 'read_file', description: 'Read one file' }, { name: 'thaliris_task_close', description: 'Reserved' }], toolStatus: 'ready' as const,
    templates: [role('reviewer')], templateStatus: 'ready' as const,
    sessions, workspaces, diagnosticSessionId: 'root-session', diagnostics, diagnosticStatus: 'ready' as const,
    diagnosticError: undefined, approvalStatus: 'idle', approvalReceipt: undefined, approvalError: undefined,
  }
}

function useStore<T>(store: SnapshotStore<T>) {
  return <S,>(select: (state: T) => S): S => useSyncExternalStore(store.subscribe, () => select(store.getSnapshot()), () => select(store.getSnapshot()))
}

function renderPage(editor: PolicyEditorController, native = createSnapshotStore(nativeState())) {
  const actions = {
    save: vi.fn(() => { void editor.save() }), discard: vi.fn(() => editor.discard()), refresh: vi.fn(),
    loadDiagnostics: vi.fn(), openPlugin: vi.fn(), openSession: vi.fn(), approveMemory: vi.fn(),
  }
  const face: ThalirisPageFace = {
    hooks: { policy: editor.store, native },
    edit: editor.edit.bind(editor), ...actions,
  }
  const t = (key: keyof typeof en) => en[key]
  render(<ThalirisPage {...face as never} view="page" t={t as never} usePolicy={useStore(editor.store)} useNative={useStore(native)} />)
  return { actions, native }
}

function createNativeProjectionController(catalogResponse: unknown): NativeProjectionController {
  const list = <T,>(snapshot: T) => ({ getSnapshot: () => snapshot, subscribe: () => () => {} })
  const ctx = {
    sessions: { list: list(sessions) },
    workspaces: { list: list(workspaces) },
    remote: {
      session: { modelCatalog: vi.fn(async () => catalogResponse) },
      $on: vi.fn(() => () => {}),
    },
    on: vi.fn(() => () => {}),
  }
  return new NativeProjectionController(ctx as never)
}

afterEach(cleanup)

describe('shared Thaliris settings client', () => {
  it('unwraps the native model catalog result and renders while the catalog is still empty at startup', async () => {
    const controller = createNativeProjectionController({ ok: true, value: modelCatalog })
    const editor = new PolicyEditorController(createForm().form)
    renderPage(editor, controller.store)

    expect(controller.getSnapshot().modelCatalog).toBeUndefined()
    fireEvent.click(screen.getByRole('tab', { name: en.tabRoles }))
    fireEvent.change(screen.getByLabelText(en.modelPolicy), { target: { value: 'fixed' } })
    expect(screen.getByRole('option', { name: en.noModels })).toBeTruthy()

    await act(async () => { await controller.loadModels() })

    expect(controller.getSnapshot().modelCatalog).toEqual(modelCatalog)
    expect(controller.getSnapshot().modelStatus).toBe('ready')
    expect(screen.getByRole('option', { name: 'Alpha / Fast' })).toBeTruthy()
  })

  it('renders the shared editable Web/Desktop page and persists complete role, route, Workspace, and memory policy through native CAS', async () => {
    const backing = createForm()
    const editor = new PolicyEditorController(backing.form)
    const { actions } = renderPage(editor)

    expect(screen.getByRole('tab', { name: en.tabGeneral })).toBeTruthy()
    expect((screen.getByLabelText(en.controllerPrompt) as HTMLTextAreaElement).value).toBe('Visible Controller instructions')
    fireEvent.click(screen.getByRole('tab', { name: en.tabRoles }))
    fireEvent.click(screen.getByRole('button', { name: en.addRole }))
    let roleIds = screen.getAllByLabelText(en.roleId) as HTMLInputElement[]
    fireEvent.change(roleIds[1]!, { target: { value: 'custom-writer' } })
    fireEvent.change((screen.getAllByLabelText(en.roleName) as HTMLInputElement[])[1]!, { target: { value: 'Custom writer' } })
    fireEvent.change((screen.getAllByLabelText(en.rolePrompt) as HTMLTextAreaElement[])[1]!, { target: { value: 'The entire user-written persona.' } })
    fireEvent.change(screen.getAllByLabelText(en.modelPolicy)[1]!, { target: { value: 'fixed' } })
    fireEvent.change(screen.getByLabelText(en.selectedModel), { target: { value: JSON.stringify(['alpha', 'fast']) } })
    fireEvent.change(screen.getByLabelText(en.reasoningEffort), { target: { value: 'high' } })
    fireEvent.change(screen.getAllByLabelText(en.modelPolicy)[1]!, { target: { value: 'allowed' } })
    const allowedHigh = screen.getByRole('checkbox', { name: 'Alpha / Fast (High)' }) as HTMLInputElement
    const allowedDefault = screen.getByRole('checkbox', { name: 'Alpha / Fast (Native default)' })
    expect(allowedHigh.checked).toBe(true)
    fireEvent.click(allowedDefault)
    expect(editor.getSnapshot().draft?.roles[1]?.modelPolicy.routes).toHaveLength(2)
    fireEvent.click(allowedDefault)
    expect(editor.getSnapshot().draft?.roles[1]?.modelPolicy.routes).toEqual([{ provider: 'alpha', model: 'fast', reasoningEffort: 'high' }])
    fireEvent.click(screen.getByRole('checkbox', { name: 'Beta / Accurate (Native default)' }))
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'read_file — Read one file' })[1]!)
    fireEvent.click(screen.getAllByRole('button', { name: en.duplicateRole })[1]!)
    roleIds = screen.getAllByLabelText(en.roleId) as HTMLInputElement[]
    expect(roleIds[2]!.value).toBe('custom-writer-copy')
    fireEvent.click(screen.getAllByRole('button', { name: en.duplicateRole })[1]!)
    roleIds = screen.getAllByLabelText(en.roleId) as HTMLInputElement[]
    expect(roleIds[2]!.value).toBe('custom-writer-copy-2')
    expect(roleIds[3]!.value).toBe('custom-writer-copy')
    fireEvent.click(screen.getAllByRole('button', { name: en.deleteRole })[2]!)
    fireEvent.click(screen.getAllByRole('button', { name: en.deleteRole })[0]!)
    expect(editor.getSnapshot().draft?.roles.map(item => item.id)).toEqual(['custom-writer', 'custom-writer-copy'])
    expect(editor.getSnapshot().draft?.roles[0]?.prompt).toBe('The entire user-written persona.')
    expect(editor.getSnapshot().draft?.roles[0]?.modelPolicy).toEqual({ mode: 'allowed', routes: [
      { provider: 'alpha', model: 'fast', reasoningEffort: 'high' }, { provider: 'beta', model: 'accurate' },
    ] })
    expect(editor.getSnapshot().draft?.roles[0]?.tools).toEqual(['read_file'])

    fireEvent.click(screen.getByRole('tab', { name: en.tabContext }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'workspace-1' } })
    fireEvent.click(screen.getByRole('button', { name: en.bindWorkspace }))
    fireEvent.click(screen.getAllByRole('checkbox', { name: en.roleMemoryContext })[0]!)
    expect(editor.getSnapshot().draft?.workspaces).toEqual([{ workspaceId: 'workspace-1', root: 'C:/repo', enabled: true }])
    expect(editor.getSnapshot().draft?.roles[0]?.context.memory).toBe(true)
    fireEvent.click(screen.getByRole('tab', { name: en.tabMemory }))
    expect(screen.getByRole('heading', { name: `${en.roleMemory}: Custom writer (custom-writer)` })).toBeTruthy()
    expect(screen.getByRole('heading', { name: `${en.roleMemory}: Custom writer (custom-writer-copy)` })).toBeTruthy()
    fireEvent.change(screen.getByLabelText(en.memoryMode), { target: { value: 'manual' } })
    expect(editor.getSnapshot().draft?.memory.mode).toBe('manual')
    fireEvent.change(screen.getByLabelText(en.memoryMode), { target: { value: 'suggest-review' } })
    expect(editor.getSnapshot().draft?.memory.mode).toBe('suggest-review')
    fireEvent.change(screen.getByLabelText(en.memoryMode), { target: { value: 'auto' } })
    fireEvent.click(screen.getByRole('checkbox', { name: en.autoAuthorized }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Provider One \(provider-one\).*Enabled for Thaliris/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: `${en.controllerRead}: Provider One` }))
    fireEvent.click(screen.getByRole('checkbox', { name: `${en.controllerWrite}: Provider One` }))
    fireEvent.click(screen.getAllByRole('checkbox', { name: `${en.roleRead}: Provider One` })[0]!)
    fireEvent.click(screen.getAllByRole('checkbox', { name: `${en.roleWrite}: Provider One` })[0]!)
    expect(editor.getSnapshot().draft?.memory).toEqual({
      mode: 'auto', autoAuthorized: true, providers: ['provider-one'],
      controllerRead: ['provider-one'], controllerWrite: ['provider-one'],
    })
    expect(editor.getSnapshot().draft?.roles[0]?.memory).toEqual({ read: ['provider-one'], write: ['provider-one'] })

    await act(async () => { await editor.save() })
    expect(backing.mutate).toHaveBeenCalledTimes(1)
    expect(backing.mutate.mock.calls[0]?.[1]).toBe(8)
    expect(backing.getSnapshot().value?.policy.roles).toHaveLength(2)
    expect(backing.getSnapshot().value?.policy.workspaces[0]?.workspaceId).toBe('workspace-1')
    expect(backing.getSnapshot().value?.policy.memory.autoAuthorized).toBe(true)
    expect(actions.save).not.toHaveBeenCalled()

    const restarted = new PolicyEditorController(backing.form)
    expect(restarted.getSnapshot().draft?.roles.map(item => item.id)).toEqual(['custom-writer', 'custom-writer-copy'])
    editor.edit('roles', [])
    await act(async () => { await editor.save() })
    const afterRestart = new PolicyEditorController(backing.form)
    expect(afterRestart.getSnapshot().draft?.roles).toEqual([])
    await Promise.all([editor.dispose(), restarted.dispose(), afterRestart.dispose()])
  })

  it('shows a conflict reload action that discards the draft and uses refreshed native Settings', async () => {
    const backing = createForm()
    const editor = new PolicyEditorController(backing.form)
    renderPage(editor)
    editor.edit('controllerPrompt', 'draft')
    const refreshed = policy()
    refreshed.controllerPrompt = 'Host refreshed guidance'
    backing.publish({ ...backing.getSnapshot(), value: { policy: refreshed }, revision: 9 })
    expect(editor.getSnapshot().conflict).toBe(true)
    expect(await editor.save()).toBe(false)
    expect(backing.mutate).not.toHaveBeenCalled()
    expect((screen.getByLabelText(en.controllerPrompt) as HTMLTextAreaElement).value).toBe('draft')
    expect(screen.getByText(en.conflict)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: en.discard }))
    expect(editor.getSnapshot().conflict).toBe(false)
    expect(editor.getSnapshot().draft?.controllerPrompt).toBe('Host refreshed guidance')
    expect((screen.getByLabelText(en.controllerPrompt) as HTMLTextAreaElement).value).toBe('Host refreshed guidance')
    await editor.dispose()
  })

  it('keeps memory-provider removal visible as editable native grants', async () => {
    const missing = policy()
    missing.memory = { mode: 'disabled', autoAuthorized: false, providers: ['gone'], controllerRead: ['gone'], controllerWrite: ['gone'] }
    const withMissingProvider = new PolicyEditorController(createForm(missing).form)
    renderPage(withMissingProvider)
    fireEvent.click(screen.getByRole('tab', { name: en.tabMemory }))
    expect(screen.getByText(`${en.providerMissing}: gone`)).toBeTruthy()
    expect(screen.getByRole('checkbox', { name: `${en.controllerRead}: gone` })).toBeTruthy()
    await withMissingProvider.dispose()
  })

  it('shows a stale allowed model route as removable when it disappears from the native catalog', async () => {
    const stale = policy()
    stale.roles[0]!.modelPolicy = { mode: 'allowed', routes: [{ provider: 'retired', model: 'old-model', reasoningEffort: 'legacy' }] }
    const editor = new PolicyEditorController(createForm(stale).form)
    renderPage(editor)
    fireEvent.click(screen.getByRole('tab', { name: en.tabRoles }))
    const retired = screen.getByRole('checkbox', { name: /retired\/old-model/ }) as HTMLInputElement
    expect(retired.checked).toBe(true)
    fireEvent.click(retired)
    expect(editor.getSnapshot().draft?.roles[0]?.modelPolicy.routes).toEqual([])
    await editor.dispose()
  })

  it('shows only native root Sessions for diagnostics, exposes proven terminal facts, and sends proposal approval only on an explicit click', async () => {
    const editor = new PolicyEditorController(createForm().form)
    const { actions, native } = renderPage(editor)
    fireEvent.click(screen.getByRole('tab', { name: en.tabDiagnostics }))
    const sessionSelect = screen.getByRole('combobox')
    expect(within(sessionSelect).getByRole('option', { name: /Root workspace/ })).toBeTruthy()
    expect(within(sessionSelect).queryByRole('option', { name: /Observed child/ })).toBeNull()
    fireEvent.change(sessionSelect, { target: { value: 'root-session' } })
    fireEvent.click(screen.getByRole('button', { name: en.refreshDiagnostics }))
    fireEvent.click(screen.getByRole('button', { name: en.openChildSession }))
    expect(actions.openSession).toHaveBeenCalledWith('child-session')
    expect(screen.getByText(/"action": "reconcile"/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: en.approveProposal }))
    expect(actions.approveMemory).toHaveBeenCalledWith('root-session', 'proposal-1')
    act(() => native.update(state => { state.approvalStatus = 'saving' }))
    expect((screen.getByRole('button', { name: en.approveProposal }) as HTMLButtonElement).disabled).toBe(true)
    act(() => native.update(state => { state.approvalStatus = 'error'; state.approvalError = 'provider-write-observed: receipt unavailable' }))
    expect(screen.getByText('provider-write-observed: receipt unavailable')).toBeTruthy()
    expect(screen.getByText(en.approvalUncertain)).toBeTruthy()
    expect(screen.getByText(en.reconcileGuide)).toBeTruthy()
    await editor.dispose()
  })

  it('renders a recorded approval receipt as evidence without creating a second proposal card', async () => {
    const editor = new PolicyEditorController(createForm().form)
    const { native } = renderPage(editor)
    const withReceipt = structuredClone(diagnostics)
    withReceipt.task.state.pending_results.push(JSON.stringify({
      approval_id: 'approval-1', proposal_id: 'proposal-1', provider: 'provider-one', workspaceId: 'workspace-1',
      outcome: 'provider-write-observed', provenance: 'native-client-approval',
    }))
    act(() => native.update(state => { state.diagnostics = withReceipt }))
    fireEvent.click(screen.getByRole('tab', { name: en.tabDiagnostics }))
    expect(screen.getAllByText(en.proposalText)).toHaveLength(1)
    expect(screen.getByText(en.alreadyApproved)).toBeTruthy()
    expect(screen.queryByRole('button', { name: en.approveProposal })).toBeNull()
    const receiptCard = screen.getByText(en.approvalReceipts).closest('article')
    expect(receiptCard?.textContent).toContain('approval-1')
    await editor.dispose()
  })

  it('renders unavailable and process-local forms as read-only', () => {
    const editor = new PolicyEditorController(createForm(policy(), false).form)
    renderPage(editor)
    expect(screen.getByText(en.readOnly)).toBeTruthy()
    expect(screen.getByLabelText(en.controllerPrompt).matches(':disabled')).toBe(true)
    expect((screen.getByRole('button', { name: en.save }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('shared client lifecycle', () => {
  it('mounts while native settings are served and removes the slot and native Gateway contribution on unload', async () => {
    const { apply, inject } = await import('../client/index.tsx')
    const ctx = new Context()
    await ctx.plugin(SlotRegistry).await()
    const slots = ctx.get('slots') as SlotRegistry
    const removeRoot = slots.register({
      name: 'root', children: { 'plugins.item': { kind: 'list', scope: 'root' } },
    } as never, () => null)
    const locale = new LocaleRuntime(ctx)
    locale.setLocale('en')
    const backing = createForm()
    const configForms = {
      get: () => backing.form,
      whileServed(_namespaces: readonly string[], register: () => () => void) { return register() },
    }
    const emptySessions = { ids: [], byId: {}, phase: 'ready', projectionsBySession: {} }
    const emptyWorkspaces = { ...workspaces, items: [] }
    const source = <T,>(initial: T) => ({ getSnapshot: () => initial, subscribe: () => () => {} })
    // Use the real Gateway namespace services: a plain remote.thaliris object
    // bypasses Cordis dependency tracing and hid the production injection bug.
    const call = vi.fn(async (_path: string, endpoint: string) => {
      const values: Record<string, unknown> = {
        'session/modelCatalog': modelCatalog,
        'thaliris/templates': [role('reviewer')],
        'thaliris/providers': [{ id: 'local', name: 'Local' }],
        'thaliris/toolCatalog': [{ name: 'read_file', description: 'Read one file' }],
        'thaliris/diagnostics': diagnostics,
        'thaliris/approveMemory': { approval_id: 'approval-1' },
      }
      if (!(endpoint in values)) throw new Error(`Unexpected endpoint: ${endpoint}`)
      return { ok: true, value: values[endpoint] }
    })
    ctx.provide('connection', {
      rpc: { call }, registerGenerationSource: () => () => {}, start: () => ({ stop: () => {} }),
    })
    await ctx.plugin(TypertRegistry)
    const gateway = ctx.plugin(Gateway)
    await gateway
    const unmountSession = await ctx.remote.$mount({ package: '@fixture/session', descriptors: [{
      ...remoteContribution.descriptors[0], id: '@fixture/session#session/modelCatalog',
      service: 'sessionController', namespace: 'session', method: 'modelCatalog',
    }] })
    ctx.provide('locale', locale)
    ctx.provide('configForms', configForms)
    ctx.provide('sessions', { list: source(emptySessions), using: vi.fn(async (_id, _options, callback) => callback()) })
    ctx.provide('workspaces', { list: source(emptyWorkspaces) })
    ctx.provide('uiWorkspace', { openSession: vi.fn() })
    ctx.provide('pluginNavigation', { openBundle: vi.fn() })
    const plugin = ctx.plugin({ inject, apply })
    await plugin.await()
    await waitFor(() => expect(slots.entries('plugins.item')).toHaveLength(1))
    const entry = slots.entries('plugins.item')[0]!
    expect(entry.options).toMatchObject({ id: 'thaliris', order: 40 })
    const face = entry.inject!() as ThalirisPageFace
    await waitFor(() => {
      expect(face.hooks.native.getSnapshot()).toMatchObject({
        modelStatus: 'ready', modelCatalog, templateStatus: 'ready', templates: [role('reviewer')],
        providerStatus: 'ready', providers: [{ id: 'local', name: 'Local' }],
        toolStatus: 'ready', tools: [{ name: 'read_file', description: 'Read one file' }],
      })
    })
    face.loadDiagnostics('root-session')
    await waitFor(() => expect(face.hooks.native.getSnapshot()).toMatchObject({ diagnosticStatus: 'ready', diagnostics }))
    face.approveMemory('root-session', 'proposal-1')
    await waitFor(() => expect(face.hooks.native.getSnapshot()).toMatchObject({ approvalStatus: 'ready', approvalReceipt: { approval_id: 'approval-1' } }))
    expect(call).toHaveBeenCalledWith('/api', 'thaliris/diagnostics', { args: { sessionId: 'root-session' } }, expect.any(AbortSignal))
    expect(call).toHaveBeenCalledWith('/api', 'thaliris/approveMemory', { args: { sessionId: 'root-session', proposalId: 'proposal-1' } }, expect.any(AbortSignal))
    expect(typeof entry.options.label === 'function' ? entry.options.label() : entry.options.label).toBe('Thaliris')
    await plugin.dispose()
    expect(slots.entries('plugins.item')).toHaveLength(0)
    expect(ctx.get('remote.thaliris')).toBeUndefined()
    await unmountSession()
    await gateway.dispose()
    removeRoot()
  })
})
