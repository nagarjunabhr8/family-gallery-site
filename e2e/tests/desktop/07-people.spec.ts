import { expect, test } from '@playwright/test'

// The generated photos contain no real faces and the throwaway data folder has no AI
// models, so this checks the People page behaves well when nobody is found yet.
// Naming, merging and correcting people is covered by backend/tests/test_people_api.py.
test('people page without faces', async ({ page }) => {
  await page.goto('/#/people')
  await expect(page.getByRole('heading', { name: 'People' })).toBeVisible()
  await expect(page.getByText(/No people yet/)).toBeVisible()
})
