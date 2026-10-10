import { expect, test } from '@playwright/test'
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { before, env } from '../support/environment'
import { diff, snapshot } from '../support/snapshot'

// Runs last (after every desktop and phone test): the app scanned, analysed, grouped,
// rotated, renamed and played the photos and songs. Not one source byte may differ.
test.describe('Read-only proof', () => {
  test('photo folder is byte-for-byte unchanged (SHA-256, size, modified time)', () => {
    const problems = diff(before().photos, snapshot(env().photos))
    expect(problems, problems.join('\n')).toEqual([])
    expect(Object.keys(before().photos).length).toBe(27)
  })

  test('music folder is unchanged', () => {
    const problems = diff(before().music, snapshot(env().music))
    expect(problems, problems.join('\n')).toEqual([])
  })

  test('the detector itself notices edits, additions and deletions (canary copy)', () => {
    const canary = join(env().root, 'canary')
    mkdirSync(canary)
    const sample = Object.keys(before().photos).find((k) => k.endsWith('.jpg'))!
    copyFileSync(join(env().photos, sample), join(canary, 'a.jpg'))
    writeFileSync(join(canary, 'b.txt'), 'b')
    const base = snapshot(canary)

    const edited = readFileSync(join(canary, 'a.jpg'))
    edited[edited.length - 1] ^= 0xff // flip one byte
    writeFileSync(join(canary, 'a.jpg'), edited)
    writeFileSync(join(canary, 'Thumbs.db'), 'x')
    rmSync(join(canary, 'b.txt'))
    expect(diff(base, snapshot(canary))).toEqual(['ADDED Thumbs.db', 'CHANGED a.jpg', 'REMOVED b.txt'])
  })

  test('everything the app generated went to its own data folder', () => {
    const data = env().data
    expect(existsSync(join(data, 'library.db'))).toBe(true)
    expect(readdirSync(join(data, 'thumbs')).length).toBeGreaterThan(0)
  })
})
