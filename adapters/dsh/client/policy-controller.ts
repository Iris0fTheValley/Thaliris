/** Revision-fenced drafts over the native Thaliris ConfigForm. */

import { createSnapshotStore, type SnapshotStore } from '@deepseek-ai/dsh-client-store'
import type { ConfigForm, ConfigFormSnapshot } from '@deepseek-ai/dsh-client-ui-settings/client'
import { z } from 'zod'
import type { RoleRecord, UserPolicy } from '../remote'

/** Exact Host namespace value: the volatile, editable field is `policy`. */
export interface ThalirisSettings { policy: UserPolicy }

export type PolicyField = 'controllerPrompt' | 'workspaces' | 'roles' | 'memory'

export interface PolicyEditorState {
  native: ConfigFormSnapshot<ThalirisSettings>
  draft: UserPolicy | undefined
  dirtyFields: readonly PolicyField[]
  saving: boolean
  conflict: boolean
  error: string | undefined
  validationError: string | undefined
  dirty: boolean
  writable: boolean
  available: boolean
}

function copyRole(value: Partial<RoleRecord>): RoleRecord {
  return {
    id: value.id ?? '',
    name: value.name ?? '',
    description: value.description ?? '',
    prompt: value.prompt ?? '',
    enabled: value.enabled ?? true,
    tools: [...(value.tools ?? [])],
    modelPolicy: {
      mode: value.modelPolicy?.mode ?? 'inherit',
      routes: structuredClone(value.modelPolicy?.routes ?? []),
    },
    memory: {
      read: [...(value.memory?.read ?? [])],
      write: [...(value.memory?.write ?? [])],
    },
    context: {
      handoff: value.context?.handoff ?? true,
      memory: value.context?.memory ?? false,
    },
  }
}

/** Fill schema-resolved defaults while keeping the native form authoritative. */
export function copyPolicy(value: Partial<UserPolicy> | undefined): UserPolicy | undefined {
  if (value === undefined) return undefined
  return {
    controllerPrompt: value.controllerPrompt ?? '',
    workspaces: structuredClone(value.workspaces ?? []),
    roles: (value.roles ?? []).map(role => copyRole(role)),
    memory: {
      mode: value.memory?.mode ?? 'disabled',
      autoAuthorized: value.memory?.autoAuthorized ?? false,
      providers: [...(value.memory?.providers ?? [])],
      controllerRead: [...(value.memory?.controllerRead ?? [])],
      controllerWrite: [...(value.memory?.controllerWrite ?? [])],
    },
  }
}

function validationError(policy: UserPolicy | undefined): string | undefined {
  if (policy === undefined) return undefined
  const ids = policy.roles.map(role => role.id.trim())
  if (ids.some(id => id.length === 0)) return 'Role IDs cannot be empty.'
  if (new Set(ids).size !== ids.length) return 'Each role needs a unique ID.'
  if (policy.roles.some(role => role.modelPolicy.mode === 'fixed' && role.modelPolicy.routes.length !== 1)) {
    return 'A fixed model policy needs exactly one allowed route.'
  }
  return undefined
}

/** Owns only transient drafts; every accepted value and write remains in native Settings. */
export class PolicyEditorController {
  readonly store: SnapshotStore<PolicyEditorState>
  private readonly dirtyFields = new Set<PolicyField>()
  private draft: UserPolicy | undefined
  private expectedRevision: number | undefined
  private saving = false
  private conflict = false
  private error: string | undefined
  private native: ConfigFormSnapshot<ThalirisSettings>
  private readonly unsubscribe: () => void

  constructor(private readonly form: ConfigForm<ThalirisSettings>) {
    this.native = form.getSnapshot()
    this.draft = copyPolicy(this.native.value?.policy)
    this.store = createSnapshotStore(this.project())
    this.unsubscribe = form.subscribe(() => this.onNativeChange())
  }

  getSnapshot = (): PolicyEditorState => this.store.getSnapshot()
  subscribe = (listener: () => void): (() => void) => this.store.subscribe(listener)

  edit<K extends PolicyField>(field: K, value: UserPolicy[K]): void {
    if (!this.canEdit()) return
    if (this.expectedRevision === undefined) this.expectedRevision = this.native.revision
    const draft = copyPolicy(this.draft)
    if (draft === undefined) return
    draft[field] = structuredClone(value)
    this.draft = draft
    this.dirtyFields.add(field)
    this.error = undefined
    this.conflict = this.native.revision !== this.expectedRevision
    this.publish()
  }

  async save(): Promise<boolean> {
    const current = this.project()
    if (!current.dirty || !current.writable || current.conflict || current.validationError
      || this.saving || this.expectedRevision === undefined || this.draft === undefined) return false
    const revision = this.expectedRevision
    const operations = [...this.dirtyFields].map(field => ({
      op: 'set' as const,
      path: ['policy', field],
      value: z.json().parse(this.draft![field]),
    }))
    this.saving = true
    this.error = undefined
    this.publish()
    try {
      const accepted = await this.form.mutate(operations, revision)
      if (!accepted) {
        this.conflict = true
        this.error = 'The native Settings revision changed. Reload its latest values before editing again.'
        return false
      }
      this.dirtyFields.clear()
      this.expectedRevision = undefined
      this.conflict = false
      this.draft = copyPolicy(this.form.getSnapshot().value?.policy)
      return true
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error)
      return false
    } finally {
      this.saving = false
      this.native = this.form.getSnapshot()
      this.publish()
    }
  }

  /** Drop this page's drafts and re-read the latest native snapshot. */
  discard(): void {
    this.native = this.form.getSnapshot()
    this.draft = copyPolicy(this.native.value?.policy)
    this.expectedRevision = undefined
    this.dirtyFields.clear()
    this.saving = false
    this.conflict = false
    this.error = undefined
    this.publish()
  }

  async dispose(): Promise<void> {
    this.unsubscribe()
  }

  private canEdit(): boolean {
    return this.native.status === 'ready' && this.native.writable && this.native.mode === 'host'
      && !this.saving && !this.conflict && this.draft !== undefined && this.native.revision !== undefined
  }

  private onNativeChange(): void {
    this.native = this.form.getSnapshot()
    if (this.saving) {
      this.publish()
      return
    }
    if (this.dirtyFields.size === 0) this.draft = copyPolicy(this.native.value?.policy)
    else if (this.native.revision !== this.expectedRevision) this.conflict = true
    this.publish()
  }

  private project(): PolicyEditorState {
    const writable = this.native.status === 'ready' && this.native.writable && this.native.mode === 'host'
    const dirtyFields = [...this.dirtyFields]
    return {
      native: this.native,
      draft: this.draft,
      dirtyFields,
      saving: this.saving,
      conflict: this.conflict,
      error: this.error,
      validationError: validationError(this.draft),
      dirty: dirtyFields.length > 0,
      writable,
      available: this.native.status === 'ready' && this.draft !== undefined,
    }
  }

  private publish(): void {
    this.store.set(this.project())
  }
}
