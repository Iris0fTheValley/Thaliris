import { writeFileSync } from 'node:fs'
import { roleTemplates } from './policy.mjs'
// Initial composition templates are stored records. An explicit [] remains empty.
writeFileSync(new URL('./cordis.patch.yml', import.meta.url), JSON.stringify([{ insert: [
  { id: 'thaliris', name: '@thaliris/dsh-plugin', disabled: true, config: { policy: { roles: roleTemplates } } },
  { id: 'thaliris-api', name: '@thaliris/dsh-plugin/api', disabled: true },
] }], null, 2) + '\n')
