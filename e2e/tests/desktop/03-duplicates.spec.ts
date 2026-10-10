import { expect, test } from '@playwright/test'

test('duplicates: review a group and change the chosen photo (nothing deleted)', async ({ page }) => {
  const before = (await (await page.request.get('/api/stats')).json()).total

  await page.goto('/#/duplicates')
  await expect(page.getByRole('heading', { name: /Duplicates/ })).toBeVisible()
  await expect(page.getByText('★ Best')).toHaveCount(2) // the burst + the party photo copies

  await page.getByRole('button', { name: 'Use this one instead' }).first().click()
  await expect(page.getByText('★ Your pick')).toHaveCount(1)

  // the choice survives a reload
  await page.reload()
  await expect(page.getByText('★ Your pick')).toHaveCount(1)

  await page.getByRole('button', { name: 'Let the app choose again' }).first().click()
  await expect(page.getByText('★ Your pick')).toHaveCount(0)

  const after = (await (await page.request.get('/api/stats')).json()).total
  expect(after).toBe(before)
})
