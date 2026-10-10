import { expect, test } from '@playwright/test'

test.describe('Occasions', () => {
  test('a family anniversary names the event on that day', async ({ page }) => {
    await page.goto('/#/occasions')
    await page.getByRole('button', { name: '+ Add a date' }).click()
    await page.getByRole('button', { name: 'Anniversary', exact: true }).click()
    await page.getByPlaceholder('e.g. Amma & Nanna').fill('Amma & Nanna')
    await page.getByLabel('Day').fill('20')
    await page.getByLabel('Month').selectOption('December')
    await page.getByLabel('Year').fill('2009')
    await page.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByRole('listitem').filter({ hasText: 'Amma & Nanna' })).toContainText('Since 2009')

    await page.goto('/#/events')
    await expect(page.getByRole('link', { name: /Amma & Nanna: 10th anniversary/ })).toBeVisible()
  })

  test('festival dates by year: linked events, edit and reset', async ({ page }) => {
    await page.goto('/#/occasions')
    const prev = page.getByRole('button', { name: '‹' })
    for (let i = 0; i < 30 && !(await page.getByText('2022', { exact: true }).isVisible()); i++) await prev.click()
    await expect(page.getByText('2022', { exact: true })).toBeVisible()

    const diwali = page.getByRole('listitem').filter({ hasText: 'Deepavali' })
    await expect(diwali).toContainText('Naraka Chaturdashi & Deepavali')
    await expect(diwali.getByRole('link', { name: /Diwali at home/ })).toBeVisible()

    const date = page.getByLabel('Deepavali date')
    await expect(date).toHaveValue('2022-10-24')
    await date.fill('2022-10-25')
    await date.blur()
    await expect(diwali.getByRole('button', { name: /edited · reset/ })).toBeVisible()
    await diwali.getByRole('button', { name: /edited · reset/ }).click()
    await expect(date).toHaveValue('2022-10-24')
  })
})
