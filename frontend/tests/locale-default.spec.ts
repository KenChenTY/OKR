import { test, expect } from '@playwright/test';

test('English is the default and explicit Chinese preference is retained', async ({ page }) => {
  await page.route('**/auth/config', route => route.fulfill({ json: { password_login: true, development_login: false } }));
  await page.route('**/api/status', route => route.fulfill({ json: { status: 'ready' } }));
  await page.goto('/login');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: 'Welcome to your workspace', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: '欢迎进入工作空间', exact: true })).toBeVisible();
});
