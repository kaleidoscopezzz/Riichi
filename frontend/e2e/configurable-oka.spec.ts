import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

// playwright.config.ts restricts all writes to the isolated localhost HTTPS QA.
const credentials = JSON.parse(readFileSync(process.env.RIICHI_QA_CREDENTIALS!, 'utf8')) as {
  username: string
  password: string
  prefix: string
}
const dialog = (page: Page) => page.getByRole('dialog')

async function select(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: option, exact: true }).click()
}

async function read(page: Page, path: string) {
  const response = await page.request.get('/api/v1' + path)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).data
}

test('configurable Oka: zero, exact decimals, automatic reset, frozen scoring and accessible themes', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/tournaments')
  await page.getByLabel('用户名', { exact: true }).fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/tournaments$/)

  const title = `${credentials.prefix} 零头名赏 ${Date.now()}`
  await page.getByRole('button', { name: '创建赛事', exact: true }).click()
  await dialog(page).getByLabel('赛事名称', { exact: true }).fill(title)
  await select(page, '总轮数', '1 轮')
  await select(page, '头名赏设置', '自定义（可为 0）')
  await expect(dialog(page).getByLabel('头名赏 Oka', { exact: true })).toHaveValue('0')
  await expect(dialog(page).getByText('0（无头名赏）', { exact: true })).toBeVisible()
  for (let index = 0; index < 4; index++) {
    const name = `${credentials.prefix} ${String(index + 1).padStart(2, '0')}`
    await page.getByRole('combobox', { name: '搜索参赛选手' }).fill(name)
    await page.getByRole('option').filter({ hasText: name }).click()
  }
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/tournaments/') && response.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '保存草稿', exact: true }).click()
  const createResponse = await created
  expect(createResponse.status()).toBe(201)
  const tournament = (await createResponse.json()).data
  const id = tournament.id as number
  expect(tournament).toMatchObject({
    oka: '0',
    oka_override: '0',
    starting_points: 25000,
    return_points: 30000,
    rules_version: 2,
  })

  async function edit() {
    await expect(dialog(page)).toHaveCount(0)
    await page.getByRole('button', { name: `查看赛事 ${title}`, exact: true }).click()
    await dialog(page).getByRole('button', { name: '编辑草稿', exact: true }).click()
  }
  async function save() {
    await dialog(page).getByRole('button', { name: '保存草稿', exact: true }).click()
    await expect(dialog(page)).toHaveCount(0)
  }

  await page.reload()
  await edit()
  await expect(dialog(page).getByLabel('头名赏 Oka', { exact: true })).toHaveValue('0')
  const preciseOka = '12.' + '1234567890'.repeat(6) + '1'
  await dialog(page).getByLabel('头名赏 Oka', { exact: true }).fill(preciseOka)
  await save()
  expect(await read(page, `/tournaments/${id}/`)).toMatchObject({
    oka: preciseOka,
    oka_override: preciseOka,
  })

  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      const rootClass = await page.locator('html').getAttribute('class')
      if ((rootClass?.includes('dark') ? 'dark' : 'light') !== theme)
        await page.getByRole('button', { name: /切换为.*主题/ }).click()
      await edit()
      const mode = page.getByRole('combobox', { name: '头名赏设置', exact: true })
      const field = dialog(page).getByLabel('头名赏 Oka', { exact: true })
      await field.scrollIntoViewIfNeeded()
      await expect(field).toHaveValue(preciseOka)
      expect(
        await dialog(page).evaluate((element) => element.scrollWidth <= element.clientWidth),
      ).toBeTruthy()
      expect(
        await page.locator('body').evaluate((element) => element.scrollWidth <= window.innerWidth),
      ).toBeTruthy()
      await page.screenshot({
        path: info.outputPath(`oka-custom-${width}-${theme}.png`),
        fullPage: false,
      })
      await mode.focus()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('listbox')).toBeVisible()
      const bounds = await page.getByRole('listbox').boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.x).toBeGreaterThanOrEqual(0)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
      await page.screenshot({
        path: info.outputPath(`oka-select-${width}-${theme}.png`),
        // Full-page capture temporarily resizes Chromium's viewport. Radix
        // intentionally closes a Select on resize, obscuring the Escape check.
        fullPage: false,
      })
      await expect(page.getByRole('listbox')).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(mode).toBeFocused()
      await dialog(page).getByRole('button', { name: '关闭赛事表单', exact: true }).click()
    }
  }

  await page.setViewportSize({ width: 1440, height: 1000 })
  await edit()
  await select(page, '头名赏设置', '自动推导')
  await dialog(page).getByLabel('开局点数', { exact: true }).fill('25001')
  await expect(dialog(page).getByText('+19.996', { exact: true })).toBeVisible()
  await save()
  expect(await read(page, `/tournaments/${id}/`)).toMatchObject({
    oka: '19.996',
    oka_override: null,
    return_points: 30000,
  })
  await edit()
  await dialog(page).getByLabel('开局点数', { exact: true }).fill('25000')
  await select(page, '头名赏设置', '自定义（可为 0）')
  await dialog(page).getByLabel('头名赏 Oka', { exact: true }).fill('0')
  await page.screenshot({ path: info.outputPath('oka-zero-config.png'), fullPage: false })
  await save()

  await page.getByRole('button', { name: `查看赛事 ${title}`, exact: true }).click()
  await dialog(page).getByRole('button', { name: '启动前检查' }).click()
  await expect(dialog(page).getByText('0（无头名赏）', { exact: true })).toBeVisible()
  await dialog(page).getByRole('button', { name: '确认启动并冻结' }).click()
  await expect(dialog(page)).toHaveCount(0)
  const csrf = await read(page, '/auth/csrf/')
  // APIRequestContext does not add the Origin header that browser fetch sends.
  const origin = new URL(page.url()).origin
  const noCsrf = await page.request.patch(`/api/v1/tournaments/${id}/`, {
    data: { oka_override: '20' },
    headers: { Origin: origin },
  })
  expect(noCsrf.status()).toBe(403)
  const frozen = await page.request.patch(`/api/v1/tournaments/${id}/`, {
    data: { oka_override: '20' },
    headers: { 'X-CSRFToken': csrf.csrf_token, Origin: origin },
  })
  expect(frozen.status()).toBe(409)

  await page.goto(`/tournaments/${id}/rounds`)
  await page.getByRole('button', { name: '选择物理桌并生成首轮' }).click()
  await select(page, '逻辑桌 A 物理桌', `800 · ${credentials.prefix} 桌1`)
  await dialog(page).getByRole('button', { name: '预览并确认' }).click()
  await dialog(page).getByRole('button', { name: '确认生成轮次' }).click()
  await expect(dialog(page)).toHaveCount(0)
  await page.getByRole('button', { name: '录入第1桌成绩', exact: true }).click()
  const points = dialog(page).getByRole('textbox', { name: /终局点数$/ })
  for (const [index, value] of ['40000', '30000', '20000', '10000'].entries())
    await points.nth(index).fill(value)
  await dialog(page).getByRole('button', { name: '确认成绩', exact: true }).click()
  await dialog(page).getByRole('button', { name: '再次确认并锁定成绩' }).click()
  await expect(dialog(page)).toHaveCount(0)
  const workspace = await read(page, `/tournaments/${id}/workspace/`)
  expect(workspace.rules).toMatchObject({ oka: '0', oka_override: '0', rules_version: 2 })
  expect(workspace.standings.map((row: { total: unknown }) => row.total)).toEqual([
    { numerator: '40', denominator: '1' },
    { numerator: '10', denominator: '1' },
    { numerator: '-20', denominator: '1' },
    { numerator: '-50', denominator: '1' },
  ])
  await page.getByRole('button', { name: '正式完赛', exact: true }).click()
  await dialog(page).getByRole('button', { name: '确认完赛并释放本场物理桌' }).click()
  await expect(dialog(page)).toHaveCount(0)
  expect(await read(page, `/tournaments/${id}/`)).toMatchObject({
    status: 'completed',
    oka: '0',
    oka_override: '0',
  })
  const final = await read(page, `/tournaments/${id}/workspace/`)
  expect(final.rules).toEqual(workspace.rules)
  expect(
    final.mapping.every((row: { history: { status: string }[] }) =>
      row.history.every((entry) => entry.status !== 'active'),
    ),
  ).toBeTruthy()
  await page.screenshot({ path: info.outputPath('oka-zero-completed.png'), fullPage: true })
  expect(errors).toEqual([])
})
