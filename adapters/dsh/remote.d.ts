import type { RemoteResult, TypertRemoteContribution, TypertRemoteNamespace } from '@deepseek-ai/dsh-typert-protocol'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'
export interface ModelRoute { provider: string; model: string; reasoningEffort?: string }
export interface RoleRecord {
  id: string; name: string; description: string; prompt: string; enabled: boolean; tools: string[];
  modelPolicy: { mode: 'inherit' | 'fixed' | 'allowed'; routes: ModelRoute[] };
  memory: { read: string[]; write: string[] }; context: { handoff: boolean; memory: boolean };
}
export interface UserPolicy {
  controllerPrompt: string;
  workspaces: { workspaceId: string; root: string; enabled: boolean }[];
  roles: RoleRecord[];
  memory: { mode: 'disabled' | 'manual' | 'suggest-review' | 'auto'; autoAuthorized: boolean; providers: string[]; controllerRead: string[]; controllerWrite: string[] };
}
export declare const remoteContribution: TypertRemoteContribution
declare module '@deepseek-ai/dsh-typert-protocol' {
  interface TypertRemoteMap {
    'thaliris/templates': () => Promise<RemoteResult<RoleRecord[]>>;
    'thaliris/providers': () => Promise<RemoteResult<{ id: string; name: string }[]>>;
    'thaliris/toolCatalog': () => Promise<RemoteResult<{ name: string; description: string }[]>>;
    'thaliris/diagnostics': (sessionId: string, signal?: AbortSignal) => Promise<RemoteResult<JsonValue>>;
    'thaliris/approveMemory': (sessionId: string, proposalId: string, signal?: AbortSignal) => Promise<RemoteResult<JsonValue>>;
  }
  interface TypertRemoteNamespaceMap { thaliris: TypertRemoteNamespace<'thaliris'> }
}
