import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { boot, createRuntimeResolution, initProfile, PluginPackages, readProfilePatches, readProfileManifest, loadProfileDirectory } from '@deepseek-ai/dsh-app-boot'
import Timer from '@deepseek-ai/cordis-plugin-timer'
import Hmr from '@deepseek-ai/dsh-hmr'
import PluginManager from '@deepseek-ai/dsh-plugin-manager'
import LocalSubprocess from '@deepseek-ai/dsh-subprocess-local'
import Storage from '@deepseek-ai/dsh-storage'
import * as StorageJson from '@deepseek-ai/dsh-storage-json'
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain'
import Registry from '@deepseek-ai/dsh-typert-registry'
import Gateway from '@deepseek-ai/dsh-api-gateway'

const packDirectory = process.env.THALIRIS_PACK_DIR!
const temporaryRoot = process.env.THALIRIS_TEST_TMP_ROOT!
const pythonExecutable = process.env.THALIRIS_TEST_PYTHON!
const corePath = process.env.THALIRIS_TEST_CORE_PATH!
assert.ok(temporaryRoot, 'THALIRIS_TEST_TMP_ROOT must keep package smoke files in the task-owned work directory')
assert.ok(pythonExecutable && existsSync(pythonExecutable), 'THALIRIS_TEST_PYTHON must name the isolated runtime Python')
assert.ok(corePath && existsSync(join(corePath, '__init__.py')), 'THALIRIS_TEST_CORE_PATH must name the installed Core wheel package')
const pythonCore = execFileSync(pythonExecutable, ['-I', '-c', 'import sys, thaliris; print(f"{sys.version_info.major}.{sys.version_info.minor}|{thaliris.__file__}")'], { encoding: 'utf8' }).trim()
const separator = pythonCore.indexOf('|')
const [pythonMajor, pythonMinor] = pythonCore.slice(0, separator).split('.').map(Number)
assert.ok(separator > 0 && (pythonMajor > 3 || pythonMajor === 3 && pythonMinor >= 11), 'installed Core wheel smoke requires Python 3.11 or newer')
assert.equal(resolve(pythonCore.slice(separator + 1)), resolve(corePath, '__init__.py'), 'runtime Python must import the installed Core wheel, not the source checkout')

mkdirSync(temporaryRoot, { recursive: true })
const home = mkdtempSync(join(temporaryRoot, 'thaliris-local-bundle-profile-'))
const profileDirectory = join(home, 'profiles', 'product')
const packSource = join(home, 'packages')
const anchor = join(home, 'package.json')
const workspaceRoot = join(home, 'workspace')
const authorityDirectory = join(home, 'authority')
const workspace = { id: 'native-workspace-smoke', path: workspaceRoot }
const tools = new Map<string, any>()
let rootAgent: any
mkdirSync(packSource, { recursive: true })
mkdirSync(workspaceRoot, { recursive: true })
mkdirSync(authorityDirectory, { recursive: true })
execFileSync('git', ['init', '-q', workspaceRoot])
writeFileSync(anchor, JSON.stringify({ name: 'thaliris-isolated-installation', private: true, dependencies: {} }, null, 2))
mkdirSync(profileDirectory, { recursive: true })
writeFileSync(join(profileDirectory, '.npmrc'), 'auto-install-peers=false\noffline=true\n')
initProfile(profileDirectory, ['core'])
const core = join(profileDirectory, 'node_modules', 'core')
mkdirSync(core, { recursive: true })
writeFileSync(join(core, 'package.json'), JSON.stringify({ name: 'core', version: '1.0.0', dsh: { bundle: { patch: './cordis.patch.yml' } } }))
writeFileSync(join(core, 'cordis.patch.yml'), JSON.stringify([{ insert: [{ id: 'manager', name: 'cordis:manager' }] }]))
const profileManifest = readProfileManifest('product', profileDirectory)
profileManifest.dependencies = {}
writeFileSync(join(profileDirectory, 'package.json'), JSON.stringify(profileManifest, null, 2))
writeFileSync(join(profileDirectory, 'cordis.yml'), '[]\n')

const archives = [
  ['@thaliris/dsh-plugin', 'thaliris-dsh-plugin-0.2.0.tgz'],
  ['@thaliris/dsh-memory', 'thaliris-dsh-memory-0.1.0.tgz'],
  ['@thaliris/dsh-memory-local', 'thaliris-dsh-memory-local-0.1.0.tgz'],
] as const
for (const [, filename] of archives) {
  const path = join(packDirectory, filename)
  assert.ok(existsSync(path), `missing local package archive: ${path}`)
  cpSync(path, join(packSource, filename))
}

const profile = {
  name: 'product',
  startedBundles: loadProfileDirectory('dsh', profileDirectory, anchor).layers.map(layer => layer.packageName),
  dir: profileDirectory,
  patchPath: join(profileDirectory, 'cordis.patch.yml'),
  installAnchor: anchor,
  cwd: home,
  home,
  overlays: [],
  telemetryDisabledEnv: undefined,
}
let owner: Awaited<ReturnType<typeof boot>> | undefined
let stopHmr: (() => Promise<void>) | undefined
let stage = 'boot'

const assertApplied = (result: { application: string; error?: unknown }, action: string): void => {
  assert.equal(result.application, 'applied', `${action} failed: ${JSON.stringify(result)}`)
}
const manager = async () => owner!.pluginManager
const bundle = async (name: string) => (await (await manager()).listBundles()).find(row => row.name === name)
const install = async (name: string, filename: string) => {
  const result = await (await manager()).installBundle(`file:./packages/${filename}`, { enabled: false })
  assertApplied(result, `install ${name}`)
  assert.equal(result.bundle, name)
  assert.equal((await bundle(name))?.enabled, false)
  assert.equal((await bundle(name))?.installed, true)
}
const enableDisableRemove = async (name: string) => {
  assertApplied(await (await manager()).setBundleEnabled(name, true), `enable ${name}`)
  assert.equal((await bundle(name))?.enabled, true)
  assertApplied(await (await manager()).setBundleEnabled(name, false), `disable ${name}`)
  assert.equal((await bundle(name))?.enabled, false)
  assertApplied(await (await manager()).removeBundle(name), `remove ${name}`)
  assert.equal(await bundle(name), undefined)
}

try {
  owner = await boot('product', join(profileDirectory, 'cordis.yml'), readProfilePatches('product', profile as never), ctx => {
    ctx.provide('appReady', { onReady: (listener: () => void) => { listener(); return () => {} } })
    ctx.provide('profileContext', profile as never)
    ctx.provide('agents', { get: (id: string) => id === rootAgent?.id ? rootAgent : undefined, roots: () => rootAgent ? [rootAgent] : [] })
    ctx.provide('systemPrompt', { getSectionOrder: () => 0, section: () => {} })
    ctx.provide('tools', {
      register: (tool: any) => { tools.set(tool.name, tool) },
      schemas: () => [...tools.values()].map(({ name, description }) => ({ name, description })),
    })
    ctx.provide('workspaceRegistry', {
      resolveByPath: async (path: string) => resolve(path) === workspaceRoot ? workspace : undefined,
      get: (id: string) => id === workspace.id ? workspace : undefined,
    })
    ctx.provide('sessionPersistence', {
      stat: async (id: string) => id === rootAgent?.id ? { header: rootAgent.session.header } : undefined,
    })
    ctx.provide('subagents', { getProvider: () => undefined })
    ctx.provide('llm', { resolveModelInfo: async () => undefined })
    ctx.loader.builtins.manager = PluginManager
  })
  await owner.plugin(Timer)
  const hmr = await owner.plugin(Hmr, { root: [], ignored: [], debounce: 0 })
  stopHmr = () => hmr.dispose()
  await owner.hmr.runExclusive(async () => {})
  await owner.plugin(LocalSubprocess)
  await owner.plugin(Storage)
  await owner.plugin(StorageJson, { root: join(home, 'storage') })
  await owner.plugin(StorageDomain, { backend: 'json' })
  await owner.plugin(Registry)
  await owner.plugin(Gateway)
  stage = 'install packages'

  rootAgent = {
    id: 'persistent-native-root-smoke',
    session: { header: { id: 'persistent-native-root-smoke', isSeeded: false, delegationDepth: 0, cwd: workspaceRoot } },
  }

  await install('@thaliris/dsh-plugin', archives[0][1])
  const installedClientRoot = join(profileDirectory, 'node_modules', '@thaliris', 'dsh-plugin')
  const installedManifest = JSON.parse(readFileSync(join(installedClientRoot, 'package.json'), 'utf8'))
  assert.equal(installedManifest.exports['./client'], './lib/client.js')
  assert.equal(installedManifest.dsh.client.platform, 'web')
  assert.ok(installedManifest.dsh.client.inject.includes('@deepseek-ai/dsh-client-ui-settings'))
  assert.match(readFileSync(join(installedClientRoot, 'lib', 'client.js'), 'utf8'), /window\.__ModuleLoader__\.load/)

  await install('@thaliris/dsh-memory', archives[1][1])
  await install('@thaliris/dsh-memory-local', archives[2][1])
  for (const name of ['@thaliris/dsh-plugin', '@thaliris/dsh-memory', '@thaliris/dsh-memory-local']) {
    assertApplied(await (await manager()).setBundleEnabled(name, true), `select ${name} bundle`)
  }
  const runtimeProfile = loadProfileDirectory('dsh', profileDirectory, anchor)
  const resolution = await createRuntimeResolution({
    installAnchor: join(process.env.DSH_SOURCE!, 'apps', 'cli', 'package.json'),
    profile: runtimeProfile,
    home,
  })
  await owner.plugin(PluginPackages, { resolution })
  stage = 'activate runtime'

  const runtimePatch = JSON.parse(readFileSync(join(installedClientRoot, 'cordis.patch.yml'), 'utf8'))[0].insert[0]
  assert.equal(runtimePatch.id, 'thaliris')

  const profileRows = new Map<string, any>()
  const savePluginOverrides = () => writeFileSync(profile.patchPath, JSON.stringify([...profileRows.values()], null, 2))
  const setPluginEnabled = async (moduleName: string, enabled: boolean, config?: unknown) => {
    const entry = owner!.loader.entries().find(item => item.options.name === moduleName)
    assert.ok(entry, `native Loader entry was not composed for ${moduleName}`)
    const id = entry.options.id
    assert.ok(id, `native Loader entry has no persistent id for ${moduleName}`)
    const prior = profileRows.get(id) ?? {}
    profileRows.set(id, { ...prior, id, name: moduleName, disabled: !enabled, ...(config === undefined ? {} : { config }) })
    savePluginOverrides()
    const listed = (await (await manager()).listPlugins()).find(row => row.moduleName === moduleName)
    assert.ok(listed, `native Plugin Manager did not expose ${moduleName}`)
    assert.ok(listed.patchId, `native Plugin Manager did not expose a persistent control for ${moduleName}`)
    const result = await (await manager()).setPluginEnabled(listed.entryId, enabled)
    assertApplied(result, `${enabled ? 'enable' : 'disable'} ${moduleName}`)
    assert.equal((await (await manager()).listPlugins()).find(row => row.entryId === listed.entryId)?.enabled, enabled)
  }

  const runtimeConfig = {
    ...runtimePatch.config,
    pythonExecutable: resolve(pythonExecutable),
    corePath: resolve(corePath),
    authorityDirectory,
    policy: {
      ...runtimePatch.config.policy,
      workspaces: [{ workspaceId: workspace.id, root: workspaceRoot, enabled: true }],
    },
  }
  await setPluginEnabled('@thaliris/dsh-plugin', true, runtimeConfig)
  stage = 'activate API and optional memory'
  assert.ok(owner.get('thaliris'), 'enabling the packed runtime must provide its native Host service')
  assert.deepEqual([...tools.keys()].sort(), [
    'thaliris_memory_propose', 'thaliris_memory_read', 'thaliris_memory_search', 'thaliris_reconcile',
    'thaliris_task_close', 'thaliris_task_inspect', 'thaliris_task_start', 'thaliris_workstream',
  ])

  await setPluginEnabled('@thaliris/dsh-plugin/api', true)
  await setPluginEnabled('@thaliris/dsh-memory', true)
  await setPluginEnabled('@thaliris/dsh-memory-local', true)
  const api = owner as any
  const apiTemplates = await api.typertGateway.invoke({ namespace: 'thaliris', method: 'templates', args: {} })
  assert.ok(apiTemplates.some((value: any) => value.id === 'curator'), 'the packed API bundle must register its native Gateway service')
  const apiTools = await api.typertGateway.invoke({ namespace: 'thaliris', method: 'toolCatalog', args: {} })
  assert.ok(apiTools.some((value: any) => value.name === 'thaliris_task_start'))
  assert.deepEqual(await api.typertGateway.invoke({ namespace: 'thaliris', method: 'providers', args: {} }), [
    { id: 'thaliris-local', name: 'Local Thaliris memory' },
  ])

  stage = 'start packed Core task'
  const execute = async (name: string, args: any) => {
    const tool = tools.get(name)
    assert.ok(tool, `runtime did not register ${name}`)
    stage = `Core ${name}`
    return tool.execute(args, { agent: rootAgent, signal: new AbortController().signal })
  }
  const started = await execute('thaliris_task_start', {
    goal: 'Packed native activation smoke',
    contract: {
      human_instruction: 'Verify the locally packed activation path', boundary: 'Task-owned temporary Git repository only',
      invariants: 'The installed Core wheel owns task intent', acceptance: 'The packed runtime can inspect and explicitly close this task',
      execution_mode: 'single-agent',
    },
  })
  assert.ok(started)
  let task: any = await execute('thaliris_task_inspect', {})
  assert.equal(task.state.status, 'ACTIVE')

  stage = 'remove optional memory and inspect task'
  await setPluginEnabled('@thaliris/dsh-plugin/api', false)
  await setPluginEnabled('@thaliris/dsh-memory-local', false)
  assert.deepEqual((owner.get('thaliris') as any).providers(), [])
  assertApplied(await (await manager()).setBundleEnabled('@thaliris/dsh-memory-local', false), 'remove local provider from profile')
  await setPluginEnabled('@thaliris/dsh-memory', false)
  assertApplied(await (await manager()).setBundleEnabled('@thaliris/dsh-memory', false), 'remove memory capability from profile')
  assert.ok(owner.get('thaliris'), 'the Core runtime must remain active after optional memory removal')
  task = await execute('thaliris_task_inspect', {})
  assert.equal(task.state.status, 'ACTIVE')
  const closed = await execute('thaliris_task_close', {
    task_id: task.state.task_id, base_revision: task.state.revision,
    decision: 'Packed runtime inspected and closed the installed-wheel task',
  })
  assert.equal(closed.status, 'DONE', 'removing default memory modules must not block close')

  stage = 'remove main runtime and bundles'
  await setPluginEnabled('@thaliris/dsh-plugin', false)
  assert.equal(owner.get('thaliris'), undefined, 'native Plugin Manager disable must unload the packed runtime')
  await enableDisableRemove('@thaliris/dsh-plugin')
  assert.equal((await bundle('@thaliris/dsh-memory-local'))?.installed, true, 'removing memory capability must not remove the local provider package')
  await enableDisableRemove('@thaliris/dsh-memory')
  await enableDisableRemove('@thaliris/dsh-memory-local')
  process.stdout.write('PASS packed bundle activation: native Plugin Manager loaded runtime, Gateway API, memory capability, and provider; task start/inspect/close used installed Core wheel and local subprocess; optional memory removal did not block close\n')
} catch (error) {
  process.stderr.write(`packed activation smoke failed during: ${stage}\n`)
  throw error
} finally {
  await stopHmr?.()
  await owner?.fiber.dispose()
  rmSync(home, { recursive: true, force: true })
}
