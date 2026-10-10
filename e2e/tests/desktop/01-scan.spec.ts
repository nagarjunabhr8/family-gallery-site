import { expect, test } from '@playwright/test'
import { env } from '../../support/environment'

test.describe('Add a photo folder and scan it', () => {
  test('rejects bad folder paths', async ({ page }) => {
    await page.goto('/#/settings')
    const input = page.getByLabel('Folder path')

    await input.fill('relative\\folder')
    await page.getByRole('button', { name: 'Add folder' }).click()
    await expect(page.getByRole('alert')).toBeVisible()

    await input.fill(env().photos + '\\does-not-exist')
    await page.getByRole('button', { name: 'Add folder' }).click()
    await expect(page.getByRole('alert')).toContainText(/exist|not found/i)
  })

  test('adds the sample folder, scans and analyses it', async ({ page }) => {
    await page.goto('/#/settings')
    // pasted like File Explorer's "Copy as path", with quotes
    await page.getByLabel('Folder path').fill(`"${env().photos}"`)
    await page.getByRole('button', { name: 'Add folder' }).click()
    const folder = page.getByRole('listitem').filter({ hasText: env().photos })
    await expect(folder).toContainText('not scanned yet')

    await page.getByRole('button', { name: 'Scan all folders' }).click()
    // the scan chains an analysis job; wait for both
    await expect(page.getByText('Last analysis finished')).toBeVisible({ timeout: 120_000 })
    await expect(page.getByText(/duplicate groups/)).toBeVisible()
    await expect(folder).toContainText('25 items')
  })

  test('re-scan is incremental', async ({ page }) => {
    const status = async () => (await page.request.get('/api/scan/status')).json()
    const previous = (await status()).last.id

    await page.goto('/#/settings')
    await page.getByRole('button', { name: 'Scan', exact: true }).click()
    // wait for a newer scan+analysis pair to finish
    await expect
      .poll(async () => {
        const s = await status()
        return s.active === null && s.last.id > previous + 1 ? s.last.kind : 'busy'
      }, { timeout: 120_000 })
      .toBe('analyze')

    const s = await status()
    expect(s.last.updated).toBe(0) // nothing new to analyse
    expect(s.last.unchanged).toBeGreaterThan(0)
    await expect(page.getByText('Last analysis finished')).toBeVisible()
  })
})
