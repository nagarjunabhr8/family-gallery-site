import { expect, test } from '@playwright/test'
import { env } from '../../support/environment'

test.describe('Our Story, best of each year, slideshow, music, dark mode', () => {
  test('home is Our Story with On this day and the timeline', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Our Story', level: 1 })).toBeVisible()
    await expect(page.getByRole('heading', { name: /On this day/ })).toBeVisible()
    await expect(page.getByText('2 years ago')).toBeVisible()
    for (const year of ['2019', '2022', '2023', '2024']) {
      await expect(page.locator(`#year-${year}`)).toBeAttached()
    }
    // no named people (synthetic photos have no faces), so chapters ask for names first
    await expect(page.getByText('Tell it in chapters')).toBeVisible()
  })

  test('best of each year and a slideshow', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: 'Best of each year' }).click()
    await expect(page).toHaveURL(/#\/best$/)
    await expect(page.getByText('Best of', { exact: true })).toBeVisible() // old page has faded out
    await page.getByRole('link', { name: '2023', exact: true }).click()
    await expect(page.getByRole('heading', { name: '2023' })).toBeVisible()
    await expect(page.getByText(/favourites out of \d+ photos/)).toBeVisible()

    await page.getByRole('button', { name: /Play 2023/ }).click()
    const show = page.getByRole('dialog', { name: 'Slideshow' })
    await expect(show).toBeVisible()
    await expect(show.getByText(/^1 \/ \d+$/)).toBeVisible()
    await page.keyboard.press('ArrowRight')
    await expect(show.getByText(/^2 \/ \d+$/)).toBeVisible()
    await expect(show.getByRole('link', { name: 'Add a music folder in Settings' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(show).toHaveCount(0)
  })

  test('music folder feeds the slideshow', async ({ page }) => {
    await page.goto('/#/settings')
    await page.getByLabel('Music folder').fill(env().music)
    await page.getByRole('button', { name: 'Use folder' }).click()
    await expect(page.getByText(/2 songs found/)).toBeVisible()

    await page.goto('/#/best/2019')
    await page.getByRole('button', { name: /Play 2019/ }).click()
    const show = page.getByRole('dialog', { name: 'Slideshow' })
    await expect(show.getByText(/Morning Raga|family song/)).toBeVisible()
    await page.keyboard.press('Escape')
  })

  test('dark mode toggle is remembered', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' })
    await page.goto('/')
    const html = page.locator('html')
    await expect(html).not.toHaveClass(/dark/)
    const toggle = page.getByRole('button', { name: /^Theme:/ })
    await toggle.click() // system -> light
    await toggle.click() // light -> dark
    await expect(html).toHaveClass(/dark/)
    await page.reload()
    await expect(html).toHaveClass(/dark/)
    await page.getByRole('button', { name: /^Theme:/ }).click() // back to system
    await expect(html).not.toHaveClass(/dark/)
  })
})
