// Source-composition runner: dependencies belong to an isolated upstream clone.
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { resolve, join } from 'node:path'
import { mkdtempSync, writeFileSync, rmSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { fileURLToPath, pathToFileURL } from 'node:url'

const source = process.env.DSH_SOURCE
const python = process.env.THALIRIS_TEST_PYTHON
if (!source || !python) throw new Error('Set DSH_SOURCE (isolated pinned clone) and THALIRIS_TEST_PYTHON (Python >=3.11).')
const revision = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' })
if (revision.status !== 0 || revision.stdout.trim() !== '639ed015397290b3745d163aafe02ffee4aa3f84') throw new Error('DSH source revision differs from the verified API baseline')
const requireSource = createRequire(resolve(source, 'package.json'))
const temp = mkdtempSync(join(tmpdir(), 'thaliris-dsh-runner-'))
const tsconfig = join(temp, 'tsconfig.json')
const requireDomain = createRequire(resolve(source, 'packages/storage/storage-domain/package.json'))
const typescript = requireSource('typescript')
const base = typescript.parseConfigFileTextToJson('tsconfig.base.json', readFileSync(resolve(source, 'tsconfig.base.json'), 'utf8')).config
const paths = Object.fromEntries(Object.entries(base.compilerOptions.paths).map(([key, values]) => [key, values.map(value => resolve(source, value))]))
writeFileSync(tsconfig, JSON.stringify({ extends: resolve(source, 'tsconfig.base.json'), compilerOptions: { paths: { ...paths, zod: [requireDomain.resolve('zod')] } } }))
try {
for (const test of (process.argv.length > 2 ? process.argv.slice(2) : ['native-loop.ts', 'product-runtime.ts'])) {
const script = fileURLToPath(new URL(test, import.meta.url))
const child = spawnSync(process.execPath, ['--import', pathToFileURL(requireSource.resolve('tsx/esm')).href, script], {
  cwd: source, stdio: 'inherit', timeout: 180000,
  env: { ...process.env, TSX_TSCONFIG_PATH: tsconfig },
})
if (child.error) throw child.error
if (child.status !== 0) { process.exitCode = child.status ?? 1; break }
}

} finally { rmSync(temp, { recursive: true, force: true }) }
