import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const credentials = JSON.parse(readFileSync(process.env.RIICHI_QA_CREDENTIALS!, 'utf8')) as {
  username: string; password: string; prefix: string
}
const name = (i: number) => `${credentials.prefix} ${String(i + 1).padStart(2, '0')}`
const dialog = (page: Page) => page.getByRole('dialog')
async function read(page: Page, path: string) {
  const response = await page.request.get('/api/v1' + path)
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  return payload.data ?? payload
}
async function select(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: option, exact: true }).click()
}

test('real browser: roster, tournaments, scores, lotteries, completion, responsive themes', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/tournaments')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('用户名', { exact: true }).fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/tournaments$/)
  await page.reload()
  await expect(page.getByRole('button', { name: '创建赛事' })).toBeVisible()

  // Exercise real player UI writes as well as seeded large-roster fixtures.
  await page.goto('/players')
  await page.getByRole('button', { name: '新增选手' }).click()
  await dialog(page).getByLabel('选手昵称').fill(credentials.prefix + ' UI新增')
  await dialog(page).getByRole('button', { name: '保存选手' }).click()
  await expect(dialog(page)).toHaveCount(0)
  await expect(page.getByText(credentials.prefix + ' UI新增', { exact: true })).toBeVisible()

  for (const [size, rounds] of [[4, 1], [8, 3], [12, 2], [16, 6], [4, 1]]) {
    const lotteryExercise = size === 4 && rounds === 1
    await page.goto('/tournaments')
    await page.getByRole('button', { name: '创建赛事' }).click()
    const title = `${credentials.prefix} ${size}人${rounds}轮 ${Date.now()}`
    await dialog(page).getByLabel('赛事名称', { exact: true }).fill(title)
    await select(page, '总轮数', `${rounds} 轮`)
    for (let i = 0; i < size; i++) {
      await page.getByRole('combobox', { name: '搜索参赛选手' }).fill(name(i))
      await page.getByRole('option').filter({ hasText: name(i) }).click()
    }
    await dialog(page).getByRole('button', { name: '保存草稿', exact: true }).click()
    await expect(dialog(page)).toHaveCount(0)
    await page.getByRole('button', { name: `查看赛事 ${title}`, exact: true }).click()
    await dialog(page).getByRole('button', { name: '启动前检查' }).click()
    await dialog(page).getByRole('button', { name: '确认启动并冻结' }).click()
    await expect(dialog(page)).toHaveCount(0)
    await page.getByRole('button', { name: `查看赛事 ${title}`, exact: true }).click()
    await dialog(page).getByRole('link', { name: '进入分桌工作台' }).click()
    await expect(page).toHaveURL(/\/tournaments\/\d+\/rounds$/)
    const id = Number(page.url().match(/tournaments\/(\d+)/)![1])
    await page.getByRole('button', { name: '选择物理桌并生成首轮' }).click()
    for (let i = 0; i < size / 4; i++)
      await select(page, `逻辑桌 ${'ABCD'[i]} 物理桌`, `${800 + i} · ${credentials.prefix} 桌${i + 1}`)
    await dialog(page).getByRole('button', { name: '预览并确认' }).click()
    await dialog(page).getByRole('button', { name: '确认生成轮次' }).click()
    await expect(dialog(page)).toHaveCount(0)
    for (let round = 1; round <= rounds; round++) {
      for (let table = 1; table <= size / 4; table++) {
        await page.getByRole('button', { name: `录入第${table}桌成绩`, exact: true }).click()
        const fields = dialog(page).getByRole('textbox', { name: /终局点数$/ })
        await expect(fields).toHaveCount(4)
        const points = size === 4 && lotteryExercise ? ['-1000', '0', '50000', '51000'] : ['25000', '25000', '25000', '25000']
        for (let i = 0; i < 4; i++) await fields.nth(i).fill(points[i])
        if (size === 4 && lotteryExercise) {
          await fields.first().fill('1e3')
          await dialog(page).getByRole('button', { name: '保存成绩草稿' }).click()
          await expect(dialog(page).getByText(/点数必须是安全范围内的整数/)).toBeVisible()
          await fields.first().fill('-１０００')
          await fields.nth(1).fill('1')
          await expect(dialog(page).getByRole('button', { name: '确认成绩', exact: true })).toBeDisabled()
          await dialog(page).getByRole('button', { name: '保存成绩草稿' }).click()
          await expect(dialog(page)).toHaveCount(0)
          await page.reload()
          await page.getByRole('button', { name: `录入第${table}桌成绩`, exact: true }).click()
          await dialog(page).getByRole('textbox', { name: /终局点数$/ }).nth(1).fill('0')
        }
        await dialog(page).getByRole('button', { name: '确认成绩', exact: true }).click()
        await dialog(page).getByRole('button', { name: '再次确认并锁定成绩' }).click()
        await expect(dialog(page)).toHaveCount(0)
        await expect(page.getByRole('button', { name: `录入第${table}桌成绩`, exact: true })).toHaveCount(0)
      }
      if (round < rounds) {
        await page.getByRole('button', { name: `生成第 ${round + 1} 轮`, exact: true }).click()
        await dialog(page).getByRole('button', { name: '预览并确认' }).click()
        await dialog(page).getByRole('button', { name: '确认生成轮次' }).click()
        await expect(dialog(page)).toHaveCount(0)
      }
    }
    let workspace = await read(page, `/tournaments/${id}/workspace/`)
    let exercisedVoid = false
    while (workspace.unresolved_groups.length) {
      const members = workspace.unresolved_groups[0] as number[]
      const names = members.map(pk => workspace.standings.find((row: { participant_id: number }) => row.participant_id === pk).display_name as string)
      await page.getByRole('button', { name: '记录公开抽签 1', exact: true }).click()
      async function enterDraw() {
        for (let i = 0; i < names.length; i++) await select(page, `抽签顺位 ${i + 1}`, names[i])
        await dialog(page).getByLabel('抽签方式', { exact: true }).fill('隔离QA预设顺序')
        await dialog(page).getByLabel('实际抽签时间', { exact: true }).fill(new Date().toISOString().slice(0, 16))
        await dialog(page).getByLabel('公开过程说明', { exact: true }).fill('仅隔离QA使用的公开抽签流程模拟，不代表真实赛事。')
        await dialog(page).getByRole('button', { name: '保存公开抽签记录' }).click()
        await expect(dialog(page).getByRole('heading', { name: /待二次确认的抽签记录/ })).toBeVisible()
      }
      await enterDraw()
      if (!exercisedVoid) {
        await dialog(page).getByRole('button', { name: '取消', exact: true }).click()
        await page.reload()
        await page.getByRole('button', { name: '记录公开抽签 1', exact: true }).click()
        await expect(dialog(page).getByRole('button', { name: '保存公开抽签记录' })).toHaveCount(0)
        await dialog(page).getByRole('button', { name: '作废此记录' }).click()
        await dialog(page).getByLabel('作废原因', { exact: true }).fill('隔离QA模拟录入纠正')
        await dialog(page).getByRole('button', { name: '预览作废' }).click()
        await dialog(page).getByRole('button', { name: '确认作废', exact: true }).click()
        await expect(dialog(page).getByText(/隔离QA模拟录入纠正/).last()).toBeVisible()
        await enterDraw()
        exercisedVoid = true
      }
      await dialog(page).getByRole('button', { name: '二次确认抽签顺序' }).click()
      await expect(dialog(page)).toHaveCount(0)
      workspace = await read(page, `/tournaments/${id}/workspace/`)
    }
    await page.getByRole('button', { name: '正式完赛', exact: true }).click()
    await dialog(page).getByRole('button', { name: '确认完赛并释放本场物理桌' }).click()
    await expect(dialog(page)).toHaveCount(0)
    await expect.poll(async () => (await read(page, `/tournaments/${id}/`)).status).toBe('completed')
    workspace = await read(page, `/tournaments/${id}/workspace/`)
    expect(workspace.mapping.every((row: { history: { status: string }[] }) => row.history.every(h => h.status !== 'active'))).toBeTruthy()
    await page.screenshot({ path: info.outputPath(`completed-${size}-${rounds}-${id}.png`), fullPage: true })
  }
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      // The theme control is exercised through the rendered UI, without store mutation.
      const rootTheme = await page.locator('html').getAttribute('class')
      if ((rootTheme?.includes('dark') ? 'dark' : 'light') !== theme)
        await page.getByRole('button', { name: /切换为.*主题/ }).click()
      await page.goto('/tournaments')
      expect(await page.locator('body').evaluate(el => el.scrollWidth <= window.innerWidth)).toBeTruthy()
      await page.screenshot({ path: info.outputPath(`tournaments-${width}-${theme}.png`), fullPage: true })
    }
  }
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto('/tournaments')
  await expect(page).toHaveURL(/\/login$/)
  expect(errors).toEqual([])
})
