// Source-composition runner: dependencies belong to an isolated upstream clone.
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const source = process.env.DSH_SOURCE
const python = process.env.THALIRIS_TEST_PYTHON
if (!source || !python) throw new Error('Set DSH_SOURCE (isolated pinned clone) and THALIRIS_TEST_PYTHON (Python >=3.11).')
const revision = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' })
if (revision.status !== 0 || revision.stdout.trim() !== '639ed015397290b3745d163aafe02ffee4aa3f84') throw new Error('DSH source revision differs from the verified API baseline')
const requireSource = createRequire(resolve(source, 'package.json'))
const script = fileURLToPath(new URL('./native-loop.ts', import.meta.url))
const child = spawnSync(process.execPath, ['--import', pathToFileURL(requireSource.resolve('tsx/esm')).href, script], {
  cwd: source, stdio: 'inherit', timeout: 180000,
  env: { ...process.env, TSX_TSCONFIG_PATH: resolve(source, 'tsconfig.base.json') },
})
if (child.error) throw child.error
process.exitCode = child.status ?? 1
