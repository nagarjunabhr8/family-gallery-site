import { expect, test } from '@playwright/test'

test.describe('Library and viewer', () => {
  test('shows everything grouped by month, with filters', async ({ page }) => {
    await page.goto('/#/library')
    await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible()
    await expect(page.getByText(/\d+ photos · 1 videos/)).toBeVisible()
    await expect(page.getByText(/similar cop(y|ies) tucked away/)).toBeVisible()
    await expect(page.getByRole('heading', { name: /December 2019/ })).toBeVisible()

    await page.getByRole('button', { name: 'Videos' }).click()
    await expect(page.getByRole('button', { name: /VID_20240102_030405\.mp4/ })).toBeVisible()
    await expect(page.getByRole('img', { name: 'DSC_0100.jpg' })).toHaveCount(0)

    await page.getByRole('button', { name: 'All' }).click()
    await page.getByRole('button', { name: 'File date' }).click()
    await expect(page.getByRole('img', { name: 'scan.png' })).toBeVisible()
    await expect(page.getByRole('img', { name: 'DSC_0100.jpg' })).toHaveCount(0)
  })

  test('viewer: browse, info, zoom and display-only rotate', async ({ page }) => {
    await page.goto('/#/library')
    await page.getByRole('img', { name: 'DSC_0100.jpg' }).click()
    const viewer = page.getByRole('dialog', { name: 'DSC_0100.jpg' })
    await expect(viewer).toBeVisible()
    await expect(viewer.getByText('Camera (EXIF) · high confidence')).toBeVisible()
    await expect(viewer.getByText(/SampleCam S1/)).toBeVisible()

    // zoom with double-click, then out again
    const photo = viewer.getByRole('img', { name: 'DSC_0100.jpg' })
    await photo.dblclick()
    await expect(photo).toHaveAttribute('style', /scale\(2\.4\)/)
    await photo.dblclick()
    await expect(photo).toHaveAttribute('style', /scale\(1\)/)

    // rotate: stored in the app only
    const id = Number((await photo.getAttribute('src'))!.match(/media\/(\d+)\//)![1])
    await viewer.getByRole('button', { name: /Rotate/ }).click()
    await expect(photo).toHaveAttribute('style', /rotate\(90deg\)/)
    await expect.poll(async () => (await (await page.request.get(`/api/media/${id}`)).json()).rotation).toBe(90)
    for (let i = 0; i < 3; i++) await viewer.getByRole('button', { name: /Rotate/ }).click()
    await expect.poll(async () => (await (await page.request.get(`/api/media/${id}`)).json()).rotation).toBe(0)

    // keyboard navigation and close
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('dialog')).not.toHaveAccessibleName('DSC_0100.jpg')
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
})
