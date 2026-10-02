import assert from 'node:assert/strict'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { boot, initProfile, readProfilePatches, readProfileManifest, loadProfileDirectory } from '@deepseek-ai/dsh-app-boot'
import Timer from '@deepseek-ai/cordis-plugin-timer'
import Hmr from '@deepseek-ai/dsh-hmr'
import PluginManager from '@deepseek-ai/dsh-plugin-manager'

const packDirectory = process.env.THALIRIS_PACK_DIR!
const home = mkdtempSync(join(tmpdir(), 'thaliris-local-bundle-profile-'))
const profileDirectory = join(home, 'profiles', 'product')
const packSource = join(home, 'packages')
const anchor = join(home, 'package.json')
mkdirSync(packSource, { recursive: true })
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
    ctx.loader.builtins.manager = PluginManager
  })
  await owner.plugin(Timer)
  const hmr = await owner.plugin(Hmr, { root: [], ignored: [], debounce: 0 })
  stopHmr = () => hmr.dispose()
  await owner.hmr.runExclusive(async () => {})

  await install('@thaliris/dsh-plugin', archives[0][1])
  const installedClientRoot = join(profileDirectory, 'node_modules', '@thaliris', 'dsh-plugin')
  const installedManifest = JSON.parse(readFileSync(join(installedClientRoot, 'package.json'), 'utf8'))
  assert.equal(installedManifest.exports['./client'], './lib/client.js')
  assert.equal(installedManifest.dsh.client.platform, 'web')
  assert.ok(installedManifest.dsh.client.inject.includes('@deepseek-ai/dsh-client-ui-settings'))
  assert.match(readFileSync(join(installedClientRoot, 'lib', 'client.js'), 'utf8'), /window\.__ModuleLoader__\.load/)
  await enableDisableRemove('@thaliris/dsh-plugin')

  await install('@thaliris/dsh-memory', archives[1][1])
  await install('@thaliris/dsh-memory-local', archives[2][1])
  await enableDisableRemove('@thaliris/dsh-memory')
  assert.equal((await bundle('@thaliris/dsh-memory-local'))?.installed, true, 'removing memory capability must not remove the local provider bundle')
  await enableDisableRemove('@thaliris/dsh-memory-local')
  process.stdout.write('PASS local installable bundles: native Plugin Manager installed, enabled, disabled, and independently removed all three tarballs in an isolated profile\n')
} finally {
  await stopHmr?.()
  await owner?.fiber.dispose()
  rmSync(home, { recursive: true, force: true })
}
