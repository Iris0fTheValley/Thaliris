/** Native DSH projections and the optional Thaliris Gateway contribution. */

import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type { ModelCatalog } from '@deepseek-ai/dsh-api-remotes/client'
import type { ISessions, SessionListState } from '@deepseek-ai/dsh-api-session-controller/client'
import type { IWorkspaces, WorkspaceSnapshot } from '@deepseek-ai/dsh-api-workspace-controller/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type {} from '../remote'

export interface NativeProjectionState {
  modelCatalog: ModelCatalog | undefined
  modelStatus: 'idle' | 'loading' | 'ready' | 'error'
  providers: readonly { id: string; name: string }[]
  providerStatus: 'idle' | 'loading' | 'ready' | 'error'
  tools: readonly { name: string; description: string }[]
  toolStatus: 'idle' | 'loading' | 'ready' | 'error'
  templates: readonly unknown[]
  templateStatus: 'idle' | 'loading' | 'ready' | 'error'
  sessions: SessionListState
  workspaces: WorkspaceSnapshot
  diagnosticSessionId: string | undefined
  diagnostics: unknown
  diagnosticStatus: 'idle' | 'loading' | 'ready' | 'error'
  diagnosticError: string | undefined
  approvalStatus: 'idle' | 'saving' | 'ready' | 'error'
  approvalReceipt: unknown
  approvalError: string | undefined
}

function describeError(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'object' && value !== null) {
    const record = value as Record<string, unknown>
    const detail = [record.code, record.message].filter(part => typeof part === 'string').join(': ')
    if (detail) return detail
  }
  return value instanceof Error ? value.message : String(value)
}

function remoteError(response: { ok: false; error: unknown }): string {
  return describeError(response.error)
}

/** Browser-side cache of Host projections; it stores no policy or task state. */
export class NativeProjectionController {
  readonly store: SnapshotStore<NativeProjectionState>
  private readonly stops: (() => void)[]

  constructor(private readonly ctx: Context) {
    const sessions = (ctx as unknown as { sessions: ISessions }).sessions
    const workspaces = (ctx as unknown as { workspaces: IWorkspaces }).workspaces
    this.store = createSnapshotStore<NativeProjectionState>({
      modelCatalog: undefined,
      modelStatus: 'idle',
      providers: [],
      providerStatus: 'idle',
      tools: [],
      toolStatus: 'idle',
      templates: [],
      templateStatus: 'idle',
      sessions: sessions.list.getSnapshot(),
      workspaces: workspaces.list.getSnapshot(),
      diagnosticSessionId: undefined,
      diagnostics: undefined,
      diagnosticStatus: 'idle',
      diagnosticError: undefined,
      approvalStatus: 'idle',
      approvalReceipt: undefined,
      approvalError: undefined,
    })
    const refreshModels = (): void => { void this.loadModels() }
    const refreshAll = (): void => { void this.refresh() }
    this.stops = [
      sessions.list.subscribe(() => {
        this.store.update(state => { state.sessions = sessions.list.getSnapshot() })
      }),
      workspaces.list.subscribe(() => {
        this.store.update(state => { state.workspaces = workspaces.list.getSnapshot() })
      }),
      ctx.remote.$on('llm/adapters-updated', refreshModels),
      ctx.remote.$on('settings/document-updated', refreshModels),
      ctx.on('connection/reset', refreshAll),
    ]
  }

  getSnapshot = (): NativeProjectionState => this.store.getSnapshot()
  subscribe = (listener: () => void): (() => void) => this.store.subscribe(listener)

  async refresh(): Promise<void> {
    await Promise.all([this.loadModels(), this.loadProviders(), this.loadTools(), this.loadTemplates()])
  }

  async loadModels(): Promise<void> {
    this.store.update(state => { state.modelStatus = 'loading' })
    try {
      const catalog = await this.ctx.remote.session.modelCatalog()
      this.store.update(state => { state.modelCatalog = catalog; state.modelStatus = 'ready' })
    } catch {
      this.store.update(state => { state.modelStatus = 'error' })
    }
  }

  async loadProviders(): Promise<void> {
    this.store.update(state => { state.providerStatus = 'loading' })
    try {
      const response = await this.ctx.remote.thaliris.providers()
      if (!response.ok) throw new Error(remoteError(response))
      this.store.update(state => { state.providers = response.value; state.providerStatus = 'ready' })
    } catch {
      this.store.update(state => { state.providerStatus = 'error' })
    }
  }

  async loadTools(): Promise<void> {
    this.store.update(state => { state.toolStatus = 'loading' })
    try {
      const response = await this.ctx.remote.thaliris.toolCatalog()
      if (!response.ok) throw new Error(remoteError(response))
      this.store.update(state => { state.tools = response.value; state.toolStatus = 'ready' })
    } catch {
      this.store.update(state => { state.toolStatus = 'error' })
    }
  }

  async loadTemplates(): Promise<void> {
    this.store.update(state => { state.templateStatus = 'loading' })
    try {
      const response = await this.ctx.remote.thaliris.templates()
      if (!response.ok) throw new Error(remoteError(response))
      this.store.update(state => { state.templates = response.value; state.templateStatus = 'ready' })
    } catch {
      this.store.update(state => { state.templateStatus = 'error' })
    }
  }

  async loadDiagnostics(sessionId: string): Promise<boolean> {
    this.store.update(state => {
      state.diagnosticSessionId = sessionId
      state.diagnosticStatus = 'loading'
      state.diagnosticError = undefined
      state.diagnostics = undefined
    })
    try {
      const sessions = (this.ctx as unknown as { sessions: ISessions }).sessions
      const response = await sessions.using(sessionId as SessionId, { source: 'gateway' }, async () => {
        return await this.ctx.remote.thaliris.diagnostics(sessionId)
      })
      if (!response.ok) throw new Error(remoteError(response))
      this.store.update(state => { state.diagnostics = response.value; state.diagnosticStatus = 'ready' })
      return true
    } catch (error) {
      this.store.update(state => {
        state.diagnosticError = describeError(error)
        state.diagnosticStatus = 'error'
      })
      return false
    }
  }

  async approveMemory(sessionId: string, proposalId: string): Promise<boolean> {
    if (this.store.getSnapshot().approvalStatus === 'saving') return false
    this.store.update(state => {
      state.approvalStatus = 'saving'
      state.approvalReceipt = undefined
      state.approvalError = undefined
    })
    try {
      const sessions = (this.ctx as unknown as { sessions: ISessions }).sessions
      const response = await sessions.using(sessionId as SessionId, { source: 'gateway' }, async () => {
        return await this.ctx.remote.thaliris.approveMemory(sessionId, proposalId)
      })
      if (!response.ok) throw new Error(remoteError(response))
      this.store.update(state => { state.approvalReceipt = response.value; state.approvalStatus = 'ready' })
      await this.loadDiagnostics(sessionId)
      return true
    } catch (error) {
      this.store.update(state => {
        state.approvalError = describeError(error)
        state.approvalStatus = 'error'
      })
      return false
    }
  }

  async dispose(): Promise<void> {
    for (const stop of this.stops) stop()
  }
}
