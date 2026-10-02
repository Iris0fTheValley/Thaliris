import { cpSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const adapterRoot = resolve(dirname(fileURLToPath(import.meta.url)))
const source = process.env.DSH_SOURCE
if (!source) throw new Error('Set DSH_SOURCE to the pinned DSH source checkout.')
const expected = '639ed015397290b3745d163aafe02ffee4aa3f84'
const revision = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' })
if (revision.status !== 0 || revision.stdout.trim() !== expected) {
  throw new Error(`DSH source revision must be ${expected}.`)
}

const workspace = resolve(source, 'packages', 'client')
const temporary = mkdtempSync(join(workspace, 'thaliris-build-'))
const relativeTemp = relative(workspace, resolve(temporary))
if (!relativeTemp || relativeTemp.startsWith(`..${sep}`) || resolve(temporary) === workspace) {
  throw new Error('Refusing to remove a temporary package outside the DSH client workspace.')
}

try {
  const src = join(temporary, 'src')
  mkdirSync(join(src, 'client'), { recursive: true })
  cpSync(join(adapterRoot, 'client'), join(src, 'client'), { recursive: true })
  copyFileSync(join(adapterRoot, 'remote.mjs'), join(src, 'remote.mjs'))
  writeFileSync(join(src, 'client', 'index.ts'), "export { apply, inject } from './index.tsx'\n")
  mkdirSync(join(temporary, 'lib', 'types'), { recursive: true })
  writeFileSync(join(temporary, 'lib', 'types', 'index.js'), 'export {}\n')
  writeFileSync(join(temporary, 'tsdown.config.ts'), `import { clientBundle } from '../tsdown.client.ts'\nexport default clientBundle('@thaliris/dsh-plugin', ['lib/types/index.js'])\n`)
  writeFileSync(join(temporary, 'package.json'), JSON.stringify({
    name: '@thaliris/dsh-plugin',
    version: '0.2.0',
    type: 'module',
    dsh: { client: {
      platform: 'web',
      inject: [
        '@deepseek-ai/dsh-api-remotes',
        '@deepseek-ai/dsh-api-session-controller',
        '@deepseek-ai/dsh-api-workspace-controller',
        '@deepseek-ai/dsh-client-locale',
        '@deepseek-ai/dsh-client-ui-plugin-manager',
        '@deepseek-ai/dsh-client-ui-settings',
        '@deepseek-ai/dsh-client-ui-workspace',
      ],
    } },
    dependencies: { zod: '^4.4.3' },
  }, null, 2))
  const nodeModules = join(temporary, 'node_modules')
  const upstreamNodeModules = join(workspace, 'ui-settings-subagent', 'node_modules')
  if (!existsSync(upstreamNodeModules)) throw new Error('Pinned DSH client dependencies are not installed.')
  symlinkSync(upstreamNodeModules, nodeModules, 'junction')

  const tsdown = join(source, 'node_modules', 'tsdown', 'dist', 'run.mjs')
  if (!existsSync(tsdown)) throw new Error('Pinned DSH client build dependencies are not installed.')
  const build = spawnSync(process.execPath, [tsdown, '--config', join(temporary, 'tsdown.config.ts')], {
    cwd: source, stdio: 'inherit', env: process.env, timeout: 180_000,
  })
  if (build.error) throw build.error
  if (build.status !== 0) process.exitCode = build.status ?? 1
  else {
    const generated = join(temporary, 'lib', 'client.js')
    const sourceMap = `${generated}.map`
    if (!existsSync(generated) || !existsSync(sourceMap)) throw new Error('The native DSH client build emitted no installable bundle or source map.')
    const output = join(adapterRoot, 'lib')
    mkdirSync(output, { recursive: true })
    copyFileSync(generated, join(output, 'client.js'))
    copyFileSync(sourceMap, join(output, 'client.js.map'))
    const map = JSON.parse(readFileSync(join(output, 'client.js.map'), 'utf8'))
    const temporaryPrefix = `../../../packages/client/${relativeTemp.split(sep).join('/')}/src/`
    map.sources = map.sources.map(sourcePath => sourcePath.replace(temporaryPrefix, '../'))
    writeFileSync(join(output, 'client.js.map'), `${JSON.stringify(map)}\n`)
  }
} finally {
  rmSync(temporary, { recursive: true, force: true })
}
