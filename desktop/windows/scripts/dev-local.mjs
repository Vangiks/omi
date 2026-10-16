// `pnpm dev:local`: `pnpm dev` against the local Docker backend (deploy/local at
// the repo root). Creates .env.local-backend from the example on first run, keeps
// the userData profile separate from the cloud one (OMI_SANDBOX=local, so local
// sign-in and data never mix with a real account), warns when the stack is down,
// then hands over to scripts/dev.mjs with `--mode local-backend`.
import { spawn } from 'node:child_process'
import { copyFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const PROFILE = '.env.local-backend'
const BACKEND_DOCS = 'http://127.0.0.1:8000/docs'

/**
 * @param {NodeJS.ProcessEnv} env
 * @returns {NodeJS.ProcessEnv}
 */
export function localDevEnv(env) {
  return { ...env, OMI_SANDBOX: env.OMI_SANDBOX || 'local' }
}

/**
 * Copies the example profile into place when missing. Never overwrites.
 * @param {string} root desktop/windows
 * @returns {boolean} true when the profile was created
 */
export function ensureLocalProfile(root) {
  const profile = join(root, PROFILE)
  if (existsSync(profile)) return false
  copyFileSync(join(root, `${PROFILE}.example`), profile)
  return true
}

/** @returns {Promise<boolean>} */
async function backendUp() {
  try {
    const res = await fetch(BACKEND_DOCS, { signal: AbortSignal.timeout(2000) })
    return res.ok
  } catch {
    return false
  }
}

async function main() {
  const root = join(dirname(fileURLToPath(import.meta.url)), '..')
  if (ensureLocalProfile(root)) console.log(`[dev:local] created ${PROFILE} from the example`)
  if (!(await backendUp())) {
    console.warn(
      `[dev:local] no backend at ${BACKEND_DOCS}. Start the stack from the repo root:\n` +
        '[dev:local]   docker compose -f deploy/local/docker-compose.yaml up -d'
    )
  }
  const child = spawn(
    process.execPath,
    [join(root, 'scripts', 'dev.mjs'), '--mode', 'local-backend', ...process.argv.slice(2)],
    { cwd: root, env: localDevEnv(process.env), stdio: 'inherit' }
  )
  process.on('SIGINT', () => child.kill('SIGINT'))
  process.on('SIGTERM', () => child.kill('SIGTERM'))
  child.on('exit', (code) => process.exit(code ?? 1))
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  void main()
}
