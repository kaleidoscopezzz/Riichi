import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

// The shared Playwright config restricts writes to isolated localhost HTTPS QA.
const credentials = JSON.parse(readFileSync(process.env.RIICHI_QA_CREDENTIALS!, 'utf8')) as {
  username: string
  password: string
  prefix: string
}
const panel = (page: Page) => page.getByRole('dialog')
async function select(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  const item = page.getByRole('option', { name: option, exact: true })
  await expect(item).toBeVisible()
  await item.click()
}
async function read(page: Page, endpoint: string) {
  const response = await page.request.get('/api/v1' + endpoint)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).data
}

test('correct earlier results while a later round is underway, preview exact scores and preserve play history', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/tournaments')
  await page.getByLabel('用户名', { exact: true }).fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/tournaments$/)
  const title = `${credentials.prefix} 成绩更正 ${Date.now()}`
  await page.getByRole('button', { name: '创建赛事', exact: true }).click()
  await panel(page).getByLabel('赛事名称', { exact: true }).fill(title)
  await select(page, '总轮数', '3 轮')
  await select(page, '头名赏设置', '自定义（可为 0）')
  for (let index = 0; index < 8; index++) {
    const name = `${credentials.prefix} ${String(index + 1).padStart(2, '0')}`
    await page.getByRole('combobox', { name: '搜索参赛选手' }).fill(name)
    await page.getByRole('option').filter({ hasText: name }).click()
  }
  const creation = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/tournaments/') && response.request().method() === 'POST',
  )
  await panel(page).getByRole('button', { name: '保存草稿', exact: true }).click()
  const id = (await (await creation).json()).data.id as number
  await expect(panel(page)).toHaveCount(0)
  await page.getByRole('button', { name: `查看赛事 ${title}`, exact: true }).click()
  await panel(page).getByRole('button', { name: '启动前检查' }).click()
  await panel(page).getByRole('button', { name: '确认启动并冻结' }).click()
  await expect(panel(page)).toHaveCount(0)
  await page.goto(`/tournaments/${id}/rounds`)
  await page.getByRole('button', { name: '选择物理桌并生成首轮' }).click()
  for (let index = 0; index < 2; index++)
    await select(
      page,
      `逻辑桌 ${'AB'[index]} 物理桌`,
      `${800 + index} · ${credentials.prefix} 桌${index + 1}`,
    )
  await panel(page).getByRole('button', { name: '预览并确认' }).click()
  const initialGeneration = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/tournaments/${id}/rounds/`) &&
      response.request().method() === 'POST',
  )
  await panel(page).getByRole('button', { name: '确认生成轮次' }).click()
  expect((await initialGeneration).status()).toBe(201)
  await expect(panel(page)).toHaveCount(0)

  async function enter(tableNumber: number, values: string[]) {
    await page.getByRole('button', { name: `录入第${tableNumber}桌成绩`, exact: true }).click()
    const fields = panel(page).getByRole('textbox', { name: /终局点数$/ })
    for (const [index, value] of values.entries()) await fields.nth(index).fill(value)
    await expect(panel(page).getByRole('region', { name: '实时积分试算' })).toContainText(
      '按本赛事规则试算',
    )
    await panel(page).getByRole('button', { name: '确认成绩', exact: true }).click()
    const confirmation = page.waitForResponse(
      (response) =>
        response.url().includes('/result/confirm/') && response.request().method() === 'POST',
    )
    await panel(page).getByRole('button', { name: '再次确认成绩', exact: true }).click()
    expect((await confirmation).status()).toBe(200)
    await expect(panel(page)).toHaveCount(0)
  }
  async function next() {
    const rounds = (await read(page, `/tournaments/${id}/rounds/`)).results
    await page.getByRole('button', { name: `生成第 ${rounds.length + 1} 轮`, exact: true }).click()
    await panel(page).getByRole('button', { name: '预览并确认' }).click()
    const generation = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/tournaments/${id}/rounds/`) &&
        response.request().method() === 'POST',
    )
    await panel(page).getByRole('button', { name: '确认生成轮次' }).click()
    expect((await generation).status()).toBe(201)
    await expect(panel(page)).toHaveCount(0)
  }

  await enter(1, ['40000', '30000', '20000', '10000'])
  await enter(2, ['25000', '25000', '25000', '25000'])
  const first = (await read(page, `/tournaments/${id}/rounds/`)).results[0]
  const firstTable = first.tables[0]
  const originalResult = await read(page, `/round-tables/${firstTable.id}/result/`)
  await next()
  await enter(1, ['40000', '30000', '20000', '10000'])
  const secondBefore = (await read(page, `/tournaments/${id}/rounds/`)).results[1]
  const mapBefore = (await read(page, `/tournaments/${id}/workspace/`)).mapping
  const firstName = firstTable.seats[0].display_name as string
  const participant = firstTable.seats[0].participant_id as number
  await select(page, '查看轮次', '第 1 轮')
  await page.getByRole('button', { name: '更正第1轮第1桌成绩', exact: true }).click()
  const fields = panel(page).getByRole('textbox', { name: /终局点数$/ })
  await expect(fields.first()).toHaveValue('40000')
  await fields.first().fill('35000')
  const card = panel(page).getByRole('article', { name: `${firstName} 积分试算`, exact: true })
  await expect(card).toContainText('终局点数 35000')
  await expect(card.getByText('35.00', { exact: true })).toBeVisible()
  await expect(panel(page).getByRole('button', { name: '保存更正', exact: true })).toBeDisabled()
  await fields.nth(1).fill('35000')
  await expect(card.getByText('25.00', { exact: true })).toBeVisible()
  await expect(card).toContainText('并列第 1 名')
  expect(await read(page, `/round-tables/${firstTable.id}/result/`)).toEqual(originalResult)
  await panel(page).getByLabel('更正说明（可选）').fill('核对原始成绩单')
  await panel(page).getByRole('button', { name: '保存更正', exact: true }).click()
  await expect(panel(page)).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: '查看轮次' })).toContainText('第 1 轮')
  const corrected = await read(page, `/round-tables/${firstTable.id}/result/`)
  expect(corrected).toMatchObject({
    version: originalResult.version + 1,
    status: 'confirmed',
    correction_count: 1,
  })
  expect(corrected.scores[0].score).toEqual({ numerator: '25', denominator: '1' })
  const roundsAfter = (await read(page, `/tournaments/${id}/rounds/`)).results
  expect(roundsAfter[1]).toEqual(secondBefore)
  const workspace = await read(page, `/tournaments/${id}/workspace/`)
  expect(workspace.mapping).toEqual(mapBefore)
  const roundTwoScore = secondBefore.tables[0].result.scores.find(
    (score: { participant_id: number }) => score.participant_id === participant,
  )
  const expectedTotal = 25n + BigInt(roundTwoScore?.score.numerator ?? '0')
  expect(
    workspace.standings.find(
      (row: { participant_id: number }) => row.participant_id === participant,
    ).total,
  ).toEqual({ numerator: String(expectedTotal), denominator: '1' })
  await page.getByRole('button', { name: '查看第1轮第1桌成绩更正记录', exact: true }).click()
  await expect(panel(page)).toContainText('点数 40000 → 35000')
  await expect(panel(page)).toContainText('积分 40.00 → 25.00')
  await expect(panel(page)).toContainText('核对原始成绩单')
  await panel(page).scrollIntoViewIfNeeded()
  const historyBounds = await panel(page).boundingBox()
  expect(historyBounds!.x).toBeGreaterThanOrEqual(0)
  expect(historyBounds!.x + historyBounds!.width).toBeLessThanOrEqual(1440)
  await page.screenshot({
    path: info.outputPath('correction-history.png'),
    fullPage: false,
    animations: 'disabled',
  })
  await panel(page).getByRole('button', { name: '关闭比赛操作', exact: true }).click()

  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      const className = await page.locator('html').getAttribute('class')
      if ((className?.includes('dark') ? 'dark' : 'light') !== theme)
        await page.getByRole('button', { name: /切换为.*主题/ }).click()
      await page.getByRole('button', { name: '更正第1轮第1桌成绩', exact: true }).click()
      const preview = panel(page).getByRole('region', { name: '实时积分试算' })
      await expect(
        preview
          .getByRole('article', { name: `${firstName} 积分试算`, exact: true })
          .getByText('25.00', { exact: true }),
      ).toBeVisible()
      await preview.scrollIntoViewIfNeeded()
      expect(
        await panel(page).evaluate((element) => element.scrollWidth <= element.clientWidth),
      ).toBeTruthy()
      expect(
        await page.locator('body').evaluate((element) => element.scrollWidth <= window.innerWidth),
      ).toBeTruthy()
      await page.screenshot({
        path: info.outputPath(`correction-preview-${width}-${theme}.png`),
        fullPage: false,
      })
      await panel(page).getByRole('button', { name: '关闭比赛操作', exact: true }).click()
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await select(page, '查看轮次', '第 2 轮')
  await enter(2, ['25000', '25000', '25000', '25000'])
  await next()
  const third = (await read(page, `/tournaments/${id}/rounds/`)).results[2]
  expect(third.generation_snapshot.source_versions).toContainEqual({
    table_id: firstTable.id,
    version: corrected.version,
  })
  await enter(1, ['40000', '30000', '20000', '10000'])
  await enter(2, ['40000', '30000', '20000', '10000'])
  let current = await read(page, `/tournaments/${id}/workspace/`)
  while (current.unresolved_groups.length) {
    const members = current.unresolved_groups[0] as number[]
    await page.getByRole('button', { name: '记录公开抽签 1', exact: true }).click()
    for (const [index, member] of members.entries())
      await select(
        page,
        `抽签顺位 ${index + 1}`,
        current.standings.find((row: { participant_id: number }) => row.participant_id === member)
          .display_name,
      )
    await panel(page).getByLabel('抽签方式', { exact: true }).fill('隔离QA签条')
    await panel(page)
      .getByLabel('实际抽签时间', { exact: true })
      .fill(new Date().toISOString().slice(0, 16))
    await panel(page)
      .getByLabel('公开过程说明', { exact: true })
      .fill('依据更正后的成绩，模拟公开抽签流程。')
    await panel(page).getByRole('button', { name: '保存公开抽签记录', exact: true }).click()
    await panel(page).getByRole('button', { name: '二次确认抽签顺序', exact: true }).click()
    await expect(panel(page)).toHaveCount(0)
    current = await read(page, `/tournaments/${id}/workspace/`)
  }
  await page.getByRole('button', { name: '正式完赛', exact: true }).click()
  await panel(page).getByRole('button', { name: '确认完赛并释放本场物理桌' }).click()
  await expect(panel(page)).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^更正第\d+轮第\d+桌成绩$/ })).toHaveCount(0)
  const final = await read(page, `/tournaments/${id}/workspace/`)
  expect(final.status).toBe('completed')
  expect(final.source_versions).toContainEqual({
    table_id: firstTable.id,
    version: corrected.version,
  })
  expect(
    final.mapping.every((table: { history: { status: string }[] }) =>
      table.history.every((row) => row.status !== 'active'),
    ),
  ).toBeTruthy()
  const token = (await read(page, '/auth/csrf/')).csrf_token
  const rejected = await page.request.post(
    `/api/v1/round-tables/${firstTable.id}/result/correct/`,
    {
      data: {
        version: corrected.version,
        points: firstTable.seats.map((seat: { participant_id: number }) => ({
          participant_id: seat.participant_id,
          raw_points: 25000,
        })),
      },
      headers: { 'X-CSRFToken': token, Origin: new URL(page.url()).origin },
    },
  )
  expect(rejected.status()).toBe(409)
  expect(await read(page, `/tournaments/${id}/workspace/`)).toEqual(final)
  await page.screenshot({ path: info.outputPath('correction-completed.png'), fullPage: true })
  expect(errors).toEqual([])
})
