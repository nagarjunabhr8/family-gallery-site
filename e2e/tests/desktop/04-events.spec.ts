import { expect, test } from '@playwright/test'

test.describe('Events', () => {
  test('festival day becomes a named event with a cover and highlights', async ({ page }) => {
    await page.goto('/#/events')
    const card = page.getByRole('link', { name: /Deepavali 2022/ })
    await expect(card).toBeVisible()
    await expect(card).toContainText('3 photos')
    await card.click()

    await expect(page.getByLabel('Event title')).toHaveValue('Deepavali 2022')
    await expect(page.getByRole('heading', { name: 'Highlights' })).toBeVisible()
    await expect(page.getByText('cover', { exact: true })).toHaveCount(1)
  })

  test('rename, add a note and pick the cover', async ({ page }) => {
    await page.goto('/#/events')
    await page.getByRole('link', { name: /Deepavali 2022/ }).click()

    const title = page.getByLabel('Event title')
    await title.fill('Diwali at home')
    await title.press('Enter')
    await page.getByPlaceholder('Add a note about this day…').fill('Lamps on every step')
    await page.getByRole('heading', { name: 'Highlights' }).click() // blur saves
    await page.reload()
    await expect(page.getByLabel('Event title')).toHaveValue('Diwali at home')
    await expect(page.getByPlaceholder('Add a note about this day…')).toHaveValue('Lamps on every step')

    await page.getByRole('button', { name: 'Select / edit' }).click()
    const all = page.locator('section').filter({ has: page.getByRole('heading', { name: 'All photos & videos' }) })
    const tile = all.getByRole('button', { name: 'IMG_20221024_192000.jpg', exact: true })
    await tile.click()
    await expect(tile).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('button', { name: 'Use as cover' }).click()
    await expect(page.getByRole('button', { name: 'Let the app choose the cover' })).toBeVisible()
    await expect(tile.getByText('cover')).toBeVisible()
  })

  test('create a custom event, split it and merge events', async ({ page }) => {
    await page.goto('/#/events')
    await page.getByRole('button', { name: '+ New event' }).click()
    await page.getByPlaceholder('e.g. Tirupati trip').fill('Summer 2023')
    await page.getByLabel('From').fill('2023-06-01')
    await page.getByLabel('To').fill('2023-06-30')
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page.getByLabel('Event title')).toHaveValue('Summer 2023')
    await expect(page.getByText(/6 photos/).first()).toBeVisible()

    // split at the afternoon party photo
    await page.getByRole('button', { name: 'Select / edit' }).click()
    await page.getByRole('button', { name: 'IMG_20230610_143000.jpg', exact: true }).first().click()
    const summerUrl = page.url()
    await page.getByRole('button', { name: 'Split from here' }).click()
    await expect(page).not.toHaveURL(summerUrl) // opens the new event
    const splitId = Number(page.url().match(/events\/(\d+)/)![1])
    const split = await (await page.request.get(`/api/events/${splitId}`)).json()
    expect(split.media.map((m: { taken_at: string }) => m.taken_at.slice(11, 16))).toEqual(
      expect.arrayContaining(['14:30']),
    )

    // merge the two halves back together from the Events page
    await page.goto('/#/events')
    await page.getByRole('button', { name: 'Merge events…' }).click()
    await page.getByRole('button', { name: /Summer 2023/ }).click()
    const escaped = split.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    await page.getByRole('button', { name: new RegExp(`^${escaped}`) }).click()
    await page.getByRole('button', { name: 'Merge into one event' }).click()
    await expect(page.getByLabel('Event title')).toHaveValue('Summer 2023')
    await expect(page.getByText(/6 photos/).first()).toBeVisible()
  })
})
