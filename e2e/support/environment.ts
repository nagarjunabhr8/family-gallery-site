/**
 * The isolated E2E world: a throwaway folder in the OS temp dir holding
 *   photos/  generated sample photos (the "source folder"; must never change)
 *   music/   two fake songs (also read-only for the app)
 *   data/    the app's data folder for this run (FM_DATA_DIR)
 *   before.json  SHA-256/size/mtime snapshot of photos/ and music/ taken before the app starts
 *
 * Created once by the Playwright runner; worker processes reuse it through FM_E2E_ROOT.
 */
import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { snapshot } from './snapshot'

export const PROJECT = resolve(__dirname, '..', '..')
export const PORT = Number(process.env.FM_E2E_PORT ?? 8799)
export const BASE_URL = `http://127.0.0.1:${PORT}`

export function python(): string {
  const win = join(PROJECT, 'backend', '.venv', 'Scripts', 'python.exe')
  return existsSync(win) ? win : join(PROJECT, 'backend', '.venv', 'bin', 'python')
}

export interface E2EEnv {
  root: string
  photos: string
  music: string
  data: string
  before: string
}

function paths(root: string): E2EEnv {
  return {
    root,
    photos: join(root, 'photos'),
    music: join(root, 'music'),
    data: join(root, 'data'),
    before: join(root, 'before.json'),
  }
}

/** Create the world on first call (runner process); later calls just return the paths. */
export function prepare(): E2EEnv {
  if (process.env.FM_E2E_ROOT) return paths(process.env.FM_E2E_ROOT)

  // earlier runs' worlds (only generated files) that Windows couldn't delete while the server ran
  for (const old of readdirSync(tmpdir()).filter((n) => n.startsWith('fm-e2e-'))) {
    try {
      rmSync(join(tmpdir(), old), { recursive: true, force: true })
    } catch {
      // still in use by another run; leave it
    }
  }

  const env = paths(mkdtempSync(join(tmpdir(), 'fm-e2e-')))
  process.env.FM_E2E_ROOT = env.root

  if (!process.env.FM_E2E_SKIP_BUILD) {
    // the app serves frontend/dist, so test the current code
    execFileSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', 'build'], {
      cwd: join(PROJECT, 'frontend'),
      stdio: 'ignore',
      shell: process.platform === 'win32',
    })
  }
  execFileSync(python(), [join(PROJECT, 'scripts', 'make_sample_photos.py'), env.photos, '--music', env.music], {
    stdio: 'inherit',
  })
  writeFileSync(env.before, JSON.stringify({ photos: snapshot(env.photos), music: snapshot(env.music) }, null, 1))
  console.log(`E2E world: ${env.root}`)
  return env
}

export function env(): E2EEnv {
  const root = process.env.FM_E2E_ROOT
  if (!root) throw new Error('FM_E2E_ROOT is not set; run tests through playwright.config.ts')
  return paths(root)
}

export function before(): { photos: Record<string, string>; music: Record<string, string> } {
  return JSON.parse(readFileSync(env().before, 'utf8'))
}
