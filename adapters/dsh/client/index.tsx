import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'
import type {} from '@deepseek-ai/dsh-api-workspace-controller/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-plugin-manager/client'
import type {} from '@deepseek-ai/dsh-client-ui-workspace/client'
import type {} from './remote-types.ts'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { ThalirisSettings } from './policy-controller.ts'
import { remoteContribution } from '../remote.mjs'
import { PolicyEditorController } from './policy-controller.ts'
import { NativeProjectionController } from './native-controller.ts'
import { ThalirisPage, type ThalirisPageFace } from './ThalirisPage.tsx'
import { en, NS, zh, type LocaleKey } from './locales.ts'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    /** Shared Web/Desktop Thaliris product settings page. */
    'settings.thaliris': LocaleKey
  }
}

export const inject = [
  'slots', 'locale', 'remote', 'remote.session', 'sessions', 'workspaces', 'uiWorkspace',
  'pluginNavigation', 'configForms',
]

/** Mount the same product page in the shared Web client used by Desktop. */
export function apply(ctx: Context): void {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'thaliris-client: dictionaries')
  ctx.effect(() => ctx.remote.$mount(remoteContribution), 'thaliris-client: native Gateway contribution')
  // The mount creates a traced Cordis service. Consume it from a dependent
  // fiber; requiring it in this mounting fiber would deadlock initialization.
  ctx.inject(['remote.thaliris'], mountPage)
}

function mountPage(ctx: Context): void {
  const policy = new PolicyEditorController(ctx.configForms.get<ThalirisSettings>('thaliris'))
  const native = new NativeProjectionController(ctx)
  const face: ThalirisPageFace = {
    hooks: { policy: policy.store, native: native.store },
    edit: policy.edit.bind(policy),
    save: () => { void policy.save() },
    discard: () => policy.discard(),
    refresh: () => { void native.refresh() },
    loadDiagnostics: sessionId => { void native.loadDiagnostics(sessionId) },
    approveMemory: (sessionId, proposalId) => { void native.approveMemory(sessionId, proposalId) },
    openPlugin: packageName => ctx.pluginNavigation.openBundle(packageName),
    openSession: sessionId => ctx.uiWorkspace.openSession(sessionId as SessionId),
  }
  ctx.effect(() => async () => {
    await Promise.all([policy.dispose(), native.dispose()])
  }, 'thaliris-client: native projection subscriptions')
  void native.refresh()
  ctx.effect(() => ctx.configForms.whileServed(['thaliris'], () => ctx.slots.inject('plugins.item', () => ctx.slots.register({
    name: 'plugins.item',
    id: 'thaliris',
    order: 40,
    label: () => ctx.locale.bind(NS)('pluginTitle'),
    locale: NS,
    inject: () => face,
  }, ThalirisPage))), 'thaliris-client: shared settings page')
}
