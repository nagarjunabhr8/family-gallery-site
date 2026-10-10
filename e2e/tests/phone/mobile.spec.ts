import { expect, test } from '@playwright/test'
import type { Locator } from '@playwright/test'

/** Synthetic one-finger swipe (Chromium supports constructing Touch objects). */
async function swipe(target: Locator, dx: number, dy = 0) {
  await target.evaluate(
    (el, [dx, dy]) => {
      const r = el.getBoundingClientRect()
      const x = r.left + r.width / 2
      const y = r.top + r.height / 2
      const touch = (cx: number, cy: number) => new Touch({ identifier: 1, target: el, clientX: cx, clientY: cy })
      el.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, touches: [touch(x, y)], changedTouches: [touch(x, y)] }))
      el.dispatchEvent(
        new TouchEvent('touchend', { bubbles: true, touches: [], changedTouches: [touch(x + dx, y + dy)] }),
      )
    },
    [dx, dy],
  )
}

test.describe('Phone', () => {
  test('menu replaces the nav bar', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'Duplicates' })).toBeHidden()
    await page.getByRole('button', { name: 'Menu' }).click()
    await page.getByRole('link', { name: 'Events' }).click()
    await expect(page).toHaveURL(/#\/events$/)
    await expect(page.getByRole('heading', { name: 'Events' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false')
  })

  test('no sideways scrolling on main pages', async ({ page }) => {
    for (const path of ['/', '/#/events', '/#/library', '/#/occasions', '/#/settings']) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1)
    }
  })

  test('viewer: swipe to browse, swipe down to close', async ({ page }) => {
    await page.goto('/#/library')
    await page.getByRole('img', { name: 'DSC_0100.jpg' }).click()
    const viewer = page.getByRole('dialog')
    const counter = viewer.getByText(/^\d+ \/ \d+$/)
    const first = await counter.textContent()

    await swipe(viewer.locator('div').first(), -200)
    await expect(counter).not.toHaveText(first!)
    await swipe(viewer.locator('div').first(), 200)
    await expect(counter).toHaveText(first!)
    await swipe(viewer.locator('div').first(), 0, 250)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })

  test('long event titles wrap instead of being cut off', async ({ page }) => {
    await page.goto('/#/events')
    await page.getByRole('link', { name: /Diwali at home/ }).click()
    const title = page.getByLabel('Event title')
    const long = 'Diwali at home with the whole family and all the cousins'
    await title.fill(long)
    await title.press('Enter')
    await page.reload() // saved, and rendered fresh
    await expect(page.getByLabel('Event title')).toHaveValue(long)
    const box = await page.getByLabel('Event title').boundingBox()
    expect(box!.height).toBeGreaterThan(60) // more than one line
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  })
})
