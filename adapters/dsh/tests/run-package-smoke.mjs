import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath, pathToFileURL } from 'node:url'

const adapterRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = process.env.DSH_SOURCE
const packDirectory = process.env.THALIRIS_PACK_DIR
if (!source || !packDirectory) throw new Error('Set DSH_SOURCE and THALIRIS_PACK_DIR to the pinned source and locally packed bundles.')
const revision = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' })
if (revision.status !== 0 || revision.stdout.trim() !== '639ed015397290b3745d163aafe02ffee4aa3f84') {
  throw new Error('DSH source revision differs from the verified install baseline.')
}
const requireSource = createRequire(resolve(source, 'package.json'))
const temp = mkdtempSync(join(tmpdir(), 'thaliris-plugin-manager-smoke-'))
const tsconfig = join(temp, 'tsconfig.json')
const requireValues = createRequire(resolve(source, 'packages/storage/storage-domain/package.json'))
const ts = requireSource('typescript')
const base = ts.parseConfigFileTextToJson('tsconfig.base.json', readFileSync(resolve(source, 'tsconfig.base.json'), 'utf8')).config
const paths = Object.fromEntries(Object.entries(base.compilerOptions.paths).map(([key, values]) => [key, values.map(value => resolve(source, value))]))
writeFileSync(tsconfig, JSON.stringify({ extends: resolve(source, 'tsconfig.base.json'), compilerOptions: {
  paths: { ...paths, zod: [requireValues.resolve('zod')] },
} }))
try {
  const child = spawnSync(process.execPath, [
    '--import', pathToFileURL(requireSource.resolve('tsx/esm')).href,
    join(adapterRoot, 'tests', 'package-manager-smoke.ts'),
  ], {
    cwd: source, stdio: 'inherit', timeout: 240_000,
    env: { ...process.env, TSX_TSCONFIG_PATH: tsconfig, THALIRIS_PACK_DIR: resolve(packDirectory) },
  })
  if (child.error) throw child.error
  if (child.status !== 0) process.exitCode = child.status ?? 1
} finally {
  rmSync(temp, { recursive: true, force: true })
}
