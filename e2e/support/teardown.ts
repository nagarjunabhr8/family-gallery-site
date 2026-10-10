import { rmSync } from 'node:fs'

/** Remove the throwaway E2E folder (generated photos + temp data). Keep it with FM_E2E_KEEP=1. */
export default function teardown() {
  const root = process.env.FM_E2E_ROOT
  if (!root || !/fm-e2e-/.test(root)) return
  if (process.env.FM_E2E_KEEP) {
    console.log(`Kept E2E folder: ${root}`)
    return
  }
  try {
    rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 })
  } catch (e) {
    // the server may still hold the database open on Windows; it's only temp files
    console.log(`Could not fully remove ${root}: ${(e as Error).message}`)
  }
}
