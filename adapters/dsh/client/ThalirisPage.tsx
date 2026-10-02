import { useId, useMemo, useState } from 'react'
import type { PropsLocale, PropsRuntime, InjectFace } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-plugin-manager/client'
import type { RoleRecord, UserPolicy } from '../remote'
import type { PolicyEditorController } from './policy-controller.ts'
import type { NativeProjectionController, NativeProjectionState } from './native-controller.ts'
import { Button, Checkbox, Input, SegmentedTabs, SettingsForm, Switch } from '@deepseek-ai/dsh-client-ui-primitives'
import type { SegmentedTab } from '@deepseek-ai/dsh-client-ui-primitives'
import type { SettingsFormShell } from '@deepseek-ai/dsh-client-ui-primitives'
import { NS, type LocaleKey } from './locales.ts'
import css from './ThalirisPage.module.css'

export interface ThalirisPageFace {
  hooks: {
    policy: PolicyEditorController['store']
    native: NativeProjectionController['store']
  }
  edit: PolicyEditorController['edit']
  save: () => void
  discard: () => void
  refresh: () => void
  loadDiagnostics: (sessionId: string) => void
  openPlugin: (packageName: string) => void
  openSession: (sessionId: string) => void
  approveMemory: (sessionId: string, proposalId: string) => void
}

type Props = PropsRuntime<'plugins.item'> & PropsLocale<typeof NS> & InjectFace<ThalirisPageFace>
type Tab = 'general' | 'roles' | 'memory' | 'context' | 'diagnostics'

const TABS: readonly { id: Tab; key: LocaleKey }[] = [
  { id: 'general', key: 'tabGeneral' }, { id: 'roles', key: 'tabRoles' },
  { id: 'memory', key: 'tabMemory' }, { id: 'context', key: 'tabContext' },
  { id: 'diagnostics', key: 'tabDiagnostics' },
]

function json(value: unknown): string {
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}

function record(value: unknown): Record<string, any> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, any> : undefined
}

function routeKey(provider: string, model: string): string {
  return JSON.stringify([provider, model])
}

function exactRouteKey(route: { provider: string; model: string; reasoningEffort?: string }): string {
  return JSON.stringify([route.provider, route.model, route.reasoningEffort ?? null])
}

function routesOf(state: NativeProjectionState) {
  return state.modelCatalog?.groups.flatMap(group => group.models.map(model => ({
    provider: group.id,
    providerName: group.name,
    model: model.id,
    modelName: model.name,
    efforts: model.reasoning?.efforts ?? [],
  }))) ?? []
}

function roleWith(role: RoleRecord, patch: Partial<RoleRecord>): RoleRecord {
  return { ...role, ...patch }
}

function duplicateRole(role: RoleRecord, roles: readonly RoleRecord[]): RoleRecord {
  const base = role.id.trim() || 'role'
  let id = `${base}-copy`
  for (let suffix = 2; roles.some(value => value.id === id); suffix++) id = `${base}-copy-${suffix}`
  return { ...structuredClone(role), id }
}

export function ThalirisPage(props: Props) {
  const { t } = props
  const policy = props.usePolicy(state => state)
  const native = props.useNative(state => state)
  const [tab, setTab] = useState<Tab>('general')
  const [templateId, setTemplateId] = useState('')
  const [workspaceId, setWorkspaceId] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [copied, setCopied] = useState(false)
  const headingId = useId()
  const draft = policy.draft
  const shell: SettingsFormShell = {
    available: policy.available,
    writable: policy.writable,
    dirty: policy.dirty && policy.writable,
    invalid: Boolean(policy.validationError) || policy.conflict,
    saving: policy.saving,
    failed: Boolean(policy.error),
  }
  const tfn = t as (key: LocaleKey) => string
  const templates = native.templates as RoleRecord[]
  const routeChoices = useMemo(() => routesOf(native), [native.modelCatalog])
  const edit = <K extends keyof UserPolicy>(field: K, value: UserPolicy[K]): void => props.edit(field as any, value as any)
  const editRole = (index: number, patch: Partial<RoleRecord>): void => {
    if (!draft) return
    const roles = draft.roles.map((role, i) => i === index ? roleWith(role, patch) : role)
    edit('roles', roles)
  }
  const editMemory = (patch: Partial<UserPolicy['memory']>): void => {
    if (draft) edit('memory', { ...draft.memory, ...patch })
  }

  if (props.view === 'summary') return t('summary')
  return (
    <div className={css.page}>
      <header className={css.header}>
        <div>
          <h2 className={css.title} id={headingId}>Thaliris</h2>
          <p className={css.summary}>{t('summary')}</p>
        </div>
        <Button onClick={props.refresh}>{t('projectionRefresh')}</Button>
      </header>
      <SegmentedTabs label={t('settingsLabel')} value={tab}
        onChange={value => setTab(value as Tab)} items={TABS.map(item => ({
          value: item.id, label: t(item.key), id: `${headingId}-tab-${item.id}`, panelId: `${headingId}-panel`,
        })) as [SegmentedTab<Tab>, ...SegmentedTab<Tab>[]]} />
      <SettingsForm labels={{
        unavailable: t('formUnavailable'), readOnly: t('readOnly'), saveFailed: t('saveFailed'),
        save: t('save'), saving: t('saving'),
      }} state={shell} onSave={props.save} onDiscard={props.discard}>
        {policy.conflict ? <p className={css.error} role="alert">{t('conflict')}</p> : null}
        {policy.validationError ? <p className={css.error} role="alert">{policy.validationError}</p> : null}
        {policy.error ? <p className={css.error} role="alert">{policy.error}</p> : null}
        {policy.available && (!policy.writable || policy.conflict) ? <Button onClick={props.discard}>{t('discard')}</Button> : null}
        <fieldset className={css.fieldset} disabled={!policy.writable}>
        <legend className={css.visuallyHidden}>{t('settingsLabel')}</legend>
        {tab === 'general' && draft ? (
          <section className={css.section}>
            <h3>{t('generalTitle')}</h3><p>{t('generalHelp')}</p>
            <label className={css.field}><span>{t('controllerPrompt')}</span>
              <textarea value={draft.controllerPrompt} onChange={event => edit('controllerPrompt', event.currentTarget.value)} />
            </label>
          </section>
        ) : null}

        {tab === 'roles' && draft ? (
          <section className={css.section}>
            <div className={css.sectionHead}><div><h3>{t('rolesTitle')}</h3><p>{t('rolesHelp')}</p></div>
              <Button variant="primary" onClick={() => edit('roles', [...draft.roles, {
                id: '', name: '', description: '', prompt: '', enabled: true, tools: [],
                modelPolicy: { mode: 'inherit', routes: [] }, memory: { read: [], write: [] },
                context: { handoff: true, memory: false },
              }])}>{t('addRole')}</Button>
            </div>
            {native.templateStatus === 'idle' || native.templateStatus === 'error'
              ? <Button onClick={() => props.refresh()}>{t('loadTemplates')}</Button> : null}
            {native.templateStatus === 'error' ? <p>{t('templateUnavailable')}</p> : null}
            {templates.length ? <div className={css.inline}>
              <select value={templateId} onChange={event => setTemplateId(event.currentTarget.value)}>
                <option value="">{t('chooseTemplate')}</option>
                {templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}
              </select>
              <Button disabled={!templateId || draft.roles.some(role => role.id === templateId)} onClick={() => {
                const template = templates.find(role => role.id === templateId)
                if (template) edit('roles', [...draft.roles, structuredClone(template)])
              }}>{t('addTemplate')}</Button>
            </div> : null}
            {draft.roles.length === 0 ? <p>{t('noRoles')}</p> : null}
            {draft.roles.map((role, index) => {
              const chosenRoutes = role.modelPolicy.routes
              const route = chosenRoutes[0]
              const selectedKey = route ? routeKey(route.provider, route.model) : ''
              const selectedChoice = routeChoices.find(candidate => routeKey(candidate.provider, candidate.model) === selectedKey)
              const routeUnavailable = role.modelPolicy.mode === 'fixed' && Boolean(route && !selectedChoice)
              const availableExactRoutes = routeChoices.flatMap(choice => [
                { ...choice, reasoningEffort: undefined, effortName: t('defaultEffort'), available: true },
                ...choice.efforts.map(effort => ({ ...choice, reasoningEffort: effort.id,
                  effortName: effort.name ?? effort.id, available: true })),
              ])
              const allowedChoices = [
                ...availableExactRoutes,
                ...chosenRoutes.filter(value => !availableExactRoutes.some(choice => exactRouteKey(choice) === exactRouteKey(value)))
                  .map(value => ({ ...value, providerName: value.provider, modelName: value.model,
                    effortName: value.reasoningEffort ?? t('defaultEffort'), available: false })),
              ]
              const updateRoute = (key: string): void => {
                const candidate = routeChoices.find(item => routeKey(item.provider, item.model) === key)
                if (!candidate) return
                const next = { provider: candidate.provider, model: candidate.model }
                editRole(index, { modelPolicy: { ...role.modelPolicy, routes: role.modelPolicy.mode === 'allowed'
                  ? [...role.modelPolicy.routes.filter(item => routeKey(item.provider, item.model) !== key), next]
                  : [next] } })
              }
              return <article className={css.card} key={`${role.id || 'draft'}-${index}`}>
                <div className={css.cardHead}><div><strong>{role.name || role.id || t('addRole')}</strong></div>
                  <Switch checked={role.enabled} label={`${t('enabled')}: ${role.name || role.id || index + 1}`}
                    onChange={enabled => editRole(index, { enabled })} />
                </div>
                <div className={css.grid}>
                  <label className={css.field}><span>{t('roleId')}</span><Input value={role.id} onChange={event => editRole(index, { id: event.currentTarget.value })} /></label>
                  <label className={css.field}><span>{t('roleName')}</span><Input value={role.name} onChange={event => editRole(index, { name: event.currentTarget.value })} /></label>
                  <label className={`${css.field} ${css.wide}`}><span>{t('roleDescription')}</span><Input value={role.description} onChange={event => editRole(index, { description: event.currentTarget.value })} /></label>
                </div>
                <label className={css.field}><span>{t('rolePrompt')}</span>
                  <textarea aria-label={t('rolePrompt')} value={role.prompt} onChange={event => editRole(index, { prompt: event.currentTarget.value })} />
                  <small>{t('rolePromptHelp')}</small></label>
                <div className={css.subsection}><h4>{t('modelPolicy')}</h4>
                  <label className={css.field}><span>{t('modelPolicy')}</span><select value={role.modelPolicy.mode} onChange={event => editRole(index, { modelPolicy: { ...role.modelPolicy,
                    mode: event.currentTarget.value as RoleRecord['modelPolicy']['mode'],
                    routes: event.currentTarget.value === 'inherit' ? [] : role.modelPolicy.routes,
                  } })}>
                    <option value="inherit">{t('inherit')}</option><option value="fixed">{t('fixed')}</option><option value="allowed">{t('allowed')}</option>
                  </select></label>
                  {role.modelPolicy.mode !== 'inherit' ? <>
                    {native.modelStatus === 'loading' ? <p>{t('modelCatalogLoading')}</p> : null}
                    {native.modelStatus !== 'ready' ? <p>{t('modelCatalogUnavailable')}</p> : null}
                    {routeUnavailable ? <p className={css.notice}>{t('unavailableRoute')}: {route?.provider}/{route?.model}</p> : null}
                    {role.modelPolicy.mode === 'fixed' ? <label className={css.field}><span>{t('selectedModel')}</span>
                      <select value={selectedKey} onChange={event => updateRoute(event.currentTarget.value)}>
                        <option value="">{t('noModels')}</option>{routeChoices.map(item => <option key={routeKey(item.provider, item.model)} value={routeKey(item.provider, item.model)}>{item.providerName} / {item.modelName}</option>)}
                      </select></label> : null}
                    {role.modelPolicy.mode === 'allowed' ? <div className={css.checkGrid}>{allowedChoices.map(item => {
                      const key = exactRouteKey(item)
                      const checked = role.modelPolicy.routes.some(value => exactRouteKey(value) === key)
                      return <div key={key} className={css.stack}>
                      <Checkbox checked={checked} label={item.available
                        ? `${item.providerName} / ${item.modelName} (${item.effortName})`
                        : `${item.provider}/${item.model} (${item.effortName}) — ${t('unavailableRoute')}`} onChange={next => {
                        const selected = role.modelPolicy.routes.filter(value => exactRouteKey(value) !== key)
                        if (next && item.available) selected.push({ provider: item.provider, model: item.model,
                          ...(item.reasoningEffort ? { reasoningEffort: item.reasoningEffort } : {}) })
                        editRole(index, { modelPolicy: { ...role.modelPolicy, routes: selected } })
                      }} />
                      </div>
                    })}</div> : null}
                    {role.modelPolicy.mode === 'fixed' && selectedChoice?.efforts.length ? <label className={css.field}><span>{t('reasoningEffort')}</span>
                      <select value={route?.reasoningEffort ?? ''} onChange={event => {
                        if (!route) return
                        const next = { provider: route.provider, model: route.model, ...(event.currentTarget.value ? { reasoningEffort: event.currentTarget.value } : {}) }
                        editRole(index, { modelPolicy: { ...role.modelPolicy, routes: [next] } })
                      }}><option value="">{t('defaultEffort')}</option>{selectedChoice.efforts.map(effort => <option key={effort.id} value={effort.id}>{effort.name ?? effort.id}</option>)}</select></label> : null}
                  </> : null}
                </div>
                <div className={css.subsection}><h4>{t('tools')}</h4>
                  {native.toolStatus !== 'ready' ? <><p>{t('toolsUnavailable')}</p>{role.tools.map(name =>
                    <Checkbox key={name} checked label={`${name} — ${t('toolUnavailable')}`} onChange={checked => {
                      if (!checked) editRole(index, { tools: role.tools.filter(value => value !== name) })
                    }} />)}</> : native.tools.length === 0 ? <><p>{t('noTools')}</p>{role.tools.map(name =>
                      <Checkbox key={name} checked label={`${name} — ${t('toolUnavailable')}`} onChange={checked => {
                        if (!checked) editRole(index, { tools: role.tools.filter(value => value !== name) })
                      }} />)}</> :
                    <div className={css.checkGrid}>{[...new Set([
                      ...native.tools.filter(tool => !tool.name.startsWith('thaliris_task_') && tool.name !== 'thaliris_reconcile' && tool.name !== 'thaliris_workstream').map(tool => tool.name),
                      ...role.tools,
                    ])].map(name => {
                      const tool = native.tools.find(item => item.name === name)
                      const reserved = name.startsWith('thaliris_task_') || name === 'thaliris_reconcile' || name === 'thaliris_workstream'
                      return <Checkbox key={name} checked={role.tools.includes(name)} disabled={reserved && !role.tools.includes(name)}
                        label={`${name}${tool?.description ? ` — ${tool.description}` : ` — ${t('toolUnavailable')}`}`} onChange={checked => {
                          const tools = role.tools.filter(value => value !== name)
                          if (checked) tools.push(name)
                          editRole(index, { tools })
                        }} />
                    })}</div>}
                </div>
                <div className={css.inlineActions}>
                  <Button onClick={() => {
                    const duplicate = duplicateRole(role, draft.roles)
                    edit('roles', [...draft.roles.slice(0, index + 1), duplicate, ...draft.roles.slice(index + 1)])
                  }}>{t('duplicateRole')}</Button>
                  <Button onClick={() => edit('roles', draft.roles.filter((_, i) => i !== index))}>{t('deleteRole')}</Button>
                </div>
                <RoleGrantControls role={role} index={index} providers={native.providers} t={tfn}
                  onRole={editRole} />
              </article>
            })}
          </section>
        ) : null}

        {tab === 'memory' && draft ? (
          <MemoryFields draft={draft} native={native} t={tfn} editMemory={editMemory}
            openPlugin={props.openPlugin} editRole={editRole} />
        ) : null}

        {tab === 'context' && draft ? (
          <section className={css.section}>
            <h3>{t('contextTitle')}</h3><p>{t('contextHelp')}</p>
            <div className={css.inline}><select value={workspaceId} onChange={event => setWorkspaceId(event.currentTarget.value)}>
              <option value="">{native.workspaces.phase === 'pending' ? t('workspaceLoading') : t('chooseWorkspace')}</option>
              {native.workspaces.items.map(workspace => <option key={workspace.workspaceId} value={workspace.workspaceId}>{workspace.title} — {workspace.path}</option>)}
            </select><Button disabled={!workspaceId || draft.workspaces.some(row => row.workspaceId === workspaceId)} onClick={() => {
              const workspace = native.workspaces.items.find(row => row.workspaceId === workspaceId)
              if (workspace) edit('workspaces', [...draft.workspaces, { workspaceId: workspace.workspaceId, root: workspace.path, enabled: true }])
            }}>{t('bindWorkspace')}</Button></div>
            {!native.workspaces.items.length && native.workspaces.phase === 'ready' ? <p>{t('noWorkspaces')}</p> : null}
            <div className={css.stack}>{draft.workspaces.map((binding, index) => {
              const workspace = native.workspaces.items.find(row => row.workspaceId === binding.workspaceId)
              return <div className={css.card} key={binding.workspaceId}>
                <div className={css.cardHead}><div><strong>{workspace?.title ?? binding.workspaceId}</strong><code>{binding.root}</code>
                  {!workspace ? <p className={css.notice}>{t('workspaceMissing')}</p> : null}</div>
                  <Switch checked={binding.enabled} label={`${t('workspaceEnabled')}: ${binding.workspaceId}`} onChange={enabled => {
                    const workspaces = [...draft.workspaces]; workspaces[index] = { ...binding, enabled }; edit('workspaces', workspaces)
                  }} />
                </div><Button onClick={() => edit('workspaces', draft.workspaces.filter((_, i) => i !== index))}>{t('removeWorkspace')}</Button>
              </div>
            })}</div>
            <h3>{t('roleHandoff')}</h3>
            {draft.roles.map((role, index) => <div className={css.permissionRow} key={role.id || index}>
              <strong>{role.name || role.id || `Role ${index + 1}`}</strong>
              <Checkbox checked={role.context.handoff} label={t('roleHandoff')} onChange={checked => editRole(index, { context: { ...role.context, handoff: checked } })} />
              <Checkbox checked={role.context.memory} label={t('roleMemoryContext')} onChange={checked => editRole(index, { context: { ...role.context, memory: checked } })} />
            </div>)}
          </section>
        ) : null}
        </fieldset>

        {tab === 'diagnostics' ? <Diagnostics native={native} selectedSession={sessionId} setSelectedSession={setSessionId}
          copied={copied} setCopied={setCopied} t={tfn} loadDiagnostics={() => sessionId && props.loadDiagnostics(sessionId)}
          openSession={props.openSession} approveMemory={props.approveMemory} /> : null}
      </SettingsForm>
    </div>
  )
}

function RoleGrantControls({ role, index, providers, t, onRole }: {
  role: RoleRecord; index: number; providers: readonly { id: string; name: string }[];
  t: (key: LocaleKey) => string; onRole: (index: number, patch: Partial<RoleRecord>) => void
}) {
  const providerIds = [...new Set([...providers.map(provider => provider.id), ...role.memory.read, ...role.memory.write])]
  return <div className={css.subsection}><h4>{t('roleMemory')}</h4>
    {providerIds.map(id => {
      const provider = providers.find(value => value.id === id)
      const name = provider?.name ?? id
      return <div className={css.permissionRow} key={id}><strong>{name} ({id})</strong>
      <Checkbox checked={role.memory.read.includes(id)} label={`${t('roleRead')}: ${name}`} onChange={checked => {
        const read = role.memory.read.filter(value => value !== id); if (checked) read.push(id)
        onRole(index, { memory: { ...role.memory, read } })
      }} />
      <Checkbox checked={role.memory.write.includes(id)} label={`${t('roleWrite')}: ${name}`} onChange={checked => {
        const write = role.memory.write.filter(value => value !== id); if (checked) write.push(id)
        onRole(index, { memory: { ...role.memory, write } })
      }} />
      {provider ? null : <p className={css.notice}>{t('providerMissing')}: {id}</p>}
    </div>})}
  </div>
}

function MemoryFields({ draft, native, t, editMemory, openPlugin, editRole }: {
  draft: UserPolicy; native: NativeProjectionState; t: (key: LocaleKey) => string;
  editMemory: (patch: Partial<UserPolicy['memory']>) => void;
  openPlugin: (packageName: string) => void;
  editRole: (index: number, patch: Partial<RoleRecord>) => void
}) {
  const memory = draft.memory
  const toggle = (field: 'providers' | 'controllerRead' | 'controllerWrite', id: string, checked: boolean): void => {
    const values = memory[field].filter(value => value !== id)
    if (checked) values.push(id)
    editMemory({ [field]: values })
  }
  return <section className={css.section}>
    <h3>{t('memoryTitle')}</h3><p>{t('memoryHelp')}</p>
    <label className={css.field}><span>{t('memoryMode')}</span>
      <select value={memory.mode} onChange={event => editMemory({ mode: event.currentTarget.value as UserPolicy['memory']['mode'] })}>
        <option value="disabled">{t('modeDisabled')}</option><option value="manual">{t('modeManual')}</option>
        <option value="suggest-review">{t('modeSuggest')}</option><option value="auto">{t('modeAuto')}</option>
      </select></label>
    <div className={css.permissionRow}><Checkbox checked={memory.autoAuthorized} label={t('autoAuthorized')}
      onChange={autoAuthorized => editMemory({ autoAuthorized })} /><small>{t('autoAuthorizedHelp')}</small></div>
    <h4>{t('providers')}</h4>
    {native.providers.length === 0 ? <p>{t('noProviders')}</p> : null}
    {[...new Set([...native.providers.map(provider => provider.id), ...memory.providers, ...memory.controllerRead, ...memory.controllerWrite])]
      .map(id => {
        const provider = native.providers.find(value => value.id === id)
        const name = provider?.name ?? id
        return <div className={css.permissionRow} key={id}>
          <Checkbox checked={memory.providers.includes(id)} label={`${name} (${id}) — ${t('providerEnabled')}`}
            onChange={checked => toggle('providers', id, checked)} />
          <Checkbox checked={memory.controllerRead.includes(id)} label={`${t('controllerRead')}: ${name}`}
            onChange={checked => toggle('controllerRead', id, checked)} />
          <Checkbox checked={memory.controllerWrite.includes(id)} label={`${t('controllerWrite')}: ${name}`}
            onChange={checked => toggle('controllerWrite', id, checked)} />
          {provider ? null : <p className={css.notice}>{t('providerMissing')}: {id}</p>}
        </div>
      })}
    <div className={css.inlineActions}>
      <Button onClick={() => openPlugin('@thaliris/dsh-memory')}>{t('openMemoryPlugin')}</Button>
      <Button onClick={() => openPlugin('@thaliris/dsh-memory-local')}>{t('openLocalPlugin')}</Button>
    </div>
    {draft.roles.map((role, index) => <RoleGrantControls key={`${role.id || 'draft'}-${index}`} role={role} index={index}
      providers={native.providers} t={t} onRole={editRole} />)}
  </section>
}

function Diagnostics({ native, selectedSession, setSelectedSession, copied, setCopied, t, loadDiagnostics, openSession, approveMemory }: {
  native: NativeProjectionState; selectedSession: string; setSelectedSession: (value: string) => void;
  copied: boolean; setCopied: (value: boolean) => void; t: (key: LocaleKey) => string;
  loadDiagnostics: () => void; openSession: (sessionId: string) => void; approveMemory: (sessionId: string, proposalId: string) => void
}) {
  const roots = native.sessions.ids.map(id => native.sessions.byId[id])
    .filter(row => row && row.parentId === undefined && row.origin !== 'subagent')
  const data = record(native.diagnostics)
  const task = record(data?.task)
  const taskState = record(task?.state)
  const pendingResults = (taskState?.pending_results ?? []).flatMap((item: unknown) => {
    try { return [typeof item === 'string' ? JSON.parse(item) : item] } catch { return [] }
  }).map(record).filter((item: Record<string, any> | undefined) => item) as Record<string, any>[]
  const proposals = pendingResults.filter(item => typeof item.proposal_id === 'string' && typeof item.approval_id !== 'string'
    && typeof item.provider === 'string' && typeof item.key === 'string' && typeof item.text === 'string' && item.provenance !== undefined)
  const approvalReceipts = pendingResults.filter(item => typeof item.approval_id === 'string' && typeof item.proposal_id === 'string')
  const reservations = Array.isArray(data?.reservations) ? data.reservations : []
  const approved = new Set(approvalReceipts.map(value => value.proposal_id))
  return <section className={css.section}>
    <h3>{t('diagnosticsTitle')}</h3><p>{t('diagnosticsHelp')}</p>
    <div className={css.inline}><select value={selectedSession} onChange={event => setSelectedSession(event.currentTarget.value)}>
      <option value="">{t('selectSession')}</option>{roots.map(row => <option key={row.id} value={row.id}>{row.displayTitle} — {row.id}</option>)}
    </select><Button disabled={!selectedSession || native.diagnosticStatus === 'loading'} onClick={loadDiagnostics}>
      {native.diagnosticStatus === 'loading' ? t('diagnosticsLoading') : native.diagnosticStatus === 'ready' ? t('refreshDiagnostics') : t('loadDiagnostics')}
    </Button></div>
    {roots.length === 0 ? <p>{t('noRootSessions')}</p> : null}
    {native.diagnosticStatus === 'error' ? <p className={css.error}>{native.diagnosticError ?? t('diagnosticsUnavailable')}</p> : null}
    {data ? <>
      <div className={css.grid}>
        <InfoCard title={t('taskEvidence')} value={task} />
        <InfoCard title={t('workspaceEvidence')} value={data.workspace} />
        <InfoCard title={t('permissionsEvidence')} value={{ permissions: data.permissions, providers: data.providers }} />
      </div>
      <h4>{t('reservationEvidence')}</h4>
      {reservations.length === 0 ? <p>{t('noReservations')}</p> : reservations.map((item: unknown, index: number) => {
        const row = record(item) ?? {}
        const reservation = record(row.reservation) ?? {}
        const observation = record(row.native) ?? {}
        const outcome = observation.outcome
        const terminal = ['completed', 'aborted', 'error', 'max-tokens', 'blocked', 'interrupted'].includes(String(outcome))
        const resident = typeof observation.reason === 'string' && observation.reason.includes('resident')
        const action = terminal ? 'reconcile' : resident ? 'cancel-reconcile' : 'check'
        const args = { task_id: taskState?.task_id, base_revision: taskState?.revision, action }
        const copy = async (): Promise<void> => {
          try { await navigator.clipboard.writeText(json(args)); setCopied(true) } catch { setCopied(false) }
        }
        return <article className={css.card} key={`${reservation.workstream ?? 'reservation'}-${index}`}>
          <strong>{reservation.workstream ?? reservation.correlation ?? t('reservationEvidence')}</strong>
          <p>{t('outcome')}: {String(outcome ?? 'UNKNOWN')}</p>
          {!terminal ? <p className={css.notice}>{t('unknownOutcome')}</p> : null}
          {observation.child_id ? <div className={css.inline}>
            <code>{String(observation.child_id)}</code><Button onClick={() => openSession(String(observation.child_id))}>{t('openChildSession')}</Button>
          </div> : null}
          <p>{t('reconcileGuide')}</p><details><summary>{t('reconcileCommand')}</summary><pre>{json(args)}</pre></details>
          <Button onClick={() => { void copy() }}>{copied ? t('commandCopied') : t('copyCommand')}</Button>
        </article>
      })}
      <h4>{t('proposals')}</h4>
      {proposals.length === 0 ? <p>{t('noProposals')}</p> : proposals.map(proposal => {
        const memory = record(data.permissions)?.memory
        const canApprove = memory && memory.mode !== 'disabled' && memory.providers?.includes(proposal.provider)
          && memory.controllerWrite?.includes(proposal.provider)
        return <article className={css.card} key={proposal.proposal_id}>
          <strong>{proposal.proposal_id}</strong>
          <p>{t('proposalProvider')}: {proposal.provider}</p><p>{t('proposalKey')}: {proposal.key}</p>
          <p>{t('proposalText')}</p><pre>{String(proposal.text ?? '')}</pre>
          <p>{t('proposalProvenance')}: {json(proposal.provenance)}</p>
          {approved.has(proposal.proposal_id) ? <p>{t('alreadyApproved')}</p> : canApprove ?
            <Button variant="primary" disabled={native.approvalStatus === 'saving'} onClick={() => approveMemory(selectedSession, proposal.proposal_id)}>{t('approveProposal')}</Button> :
            <p className={css.notice}>{t('noApprovalGrant')}</p>}
        </article>
      })}
      {approvalReceipts.length > 0 ? <InfoCard title={t('approvalReceipts')} value={approvalReceipts} /> : null}
      {native.approvalStatus === 'ready' ? <InfoCard title={t('proposalApproved')} value={native.approvalReceipt} /> : null}
      {native.approvalStatus === 'error' ? <>
        <p className={css.error}>{native.approvalError ?? t('approvalUncertain')}</p>
        {native.approvalError ? <p className={css.notice}>{t('approvalUncertain')}</p> : null}
      </> : null}
    </> : null}
  </section>
}

function InfoCard({ title, value }: { title: string; value: unknown }) {
  return <article className={css.card}><strong>{title}</strong><pre>{json(value)}</pre></article>
}
