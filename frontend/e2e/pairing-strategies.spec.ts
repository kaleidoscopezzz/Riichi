import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const credentials = JSON.parse(readFileSync(process.env.RIICHI_QA_CREDENTIALS!, 'utf8')) as {
  username: string
  password: string
  prefix: string
}
const panel = (page: Page) => page.getByRole('dialog')
async function read(page: Page, path: string) {
  const response = await page.request.get('/api/v1' + path)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).data
}
async function select(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  const item = page.getByRole('option', { name: option, exact: true })
  await expect(item).toBeVisible()
  await item.click()
}
async function login(page: Page) {
  await page.goto('/tournaments')
  await page.getByLabel('用户名', { exact: true }).fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/tournaments$/)
}
async function create(page: Page, label: string, size: number, rounds: number) {
  await page.goto('/tournaments')
  await page.getByRole('button', { name: '创建赛事', exact: true }).click()
  const title = `${credentials.prefix} ${label} ${Date.now()}`
  await panel(page).getByLabel('赛事名称', { exact: true }).fill(title)
  await select(page, '总轮数', `${rounds} 轮`)
  await select(page, '分桌策略', label)
  if (label === '高高碰') {
    await panel(page).getByLabel('A桌附加基础分').fill('5')
    await panel(page).getByLabel('B桌附加基础分').fill('2')
  }
  for (let i = 0; i < size; i++) {
    const name = `${credentials.prefix} ${String(i + 1).padStart(2, '0')}`
    await page.getByRole('combobox', { name: '搜索参赛选手' }).fill(name)
    await page.getByRole('option').filter({ hasText: name }).click()
  }
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/tournaments/') && response.request().method() === 'POST',
  )
  await panel(page).getByRole('button', { name: '保存草稿', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(201)
  const id = (await response.json()).data.id as number
  await expect(panel(page)).toHaveCount(0)
  await page.getByRole('button', { name: `查看赛事 ${title}`, exact: true }).click()
  await panel(page).getByRole('button', { name: '启动前检查' }).click()
  await panel(page).getByRole('button', { name: '确认启动并冻结' }).click()
  await expect(panel(page)).toHaveCount(0)
  await page.goto(`/tournaments/${id}/rounds`)
  return id
}
async function openGeneration(page: Page, number: number, tables: number) {
  await page
    .getByRole('button', {
      name: number === 1 ? '选择物理桌并生成首轮' : `生成第 ${number} 轮`,
      exact: true,
    })
    .click()
  if (number === 1)
    for (let i = 0; i < tables; i++)
      await select(
        page,
        `逻辑桌 ${'ABCD'[i]} 物理桌`,
        `${800 + i} · ${credentials.prefix} 桌${i + 1}`,
      )
  await expect(panel(page).getByRole('region', { name: '本轮分桌预览' })).not.toContainText(
    '正在预排',
  )
  await expect(panel(page).getByRole('article', { name: '逻辑桌 A 分组' })).toBeVisible()
}
async function publish(page: Page, id: number) {
  const groups = await panel(page)
    .locator('[data-pairing-slot]')
    .evaluateAll((elements) => {
      const groups: number[][] = []
      for (const element of elements) {
        const table = Number((element as HTMLElement).dataset.tableIndex)
        ;(groups[table] ??= []).push(Number((element as HTMLElement).dataset.pairParticipant))
      }
      return groups
    })
  await panel(page).getByRole('button', { name: '预览并确认', exact: true }).click()
  const generated = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/tournaments/${id}/rounds/`) &&
      response.request().method() === 'POST',
  )
  await panel(page).getByRole('button', { name: '确认生成轮次', exact: true }).click()
  const response = await generated
  expect(response.status()).toBe(201)
  const round = (await response.json()).data
  expect(
    round.tables.map((table: { seats: { participant_id: number }[] }) =>
      table.seats.map((seat) => seat.participant_id).sort((a, b) => a - b),
    ),
  ).toEqual(groups.map((group) => [...group].sort((a, b) => a - b)))
  await expect(panel(page)).toHaveCount(0)
  return round
}
async function record(page: Page, table: number, points: string[]) {
  await page.getByRole('button', { name: `录入第${table}桌成绩`, exact: true }).click()
  const fields = panel(page).getByRole('textbox', { name: /终局点数$/ })
  for (const [i, value] of points.entries()) await fields.nth(i).fill(value)
  await panel(page).getByRole('button', { name: '确认成绩', exact: true }).click()
  const saved = page.waitForResponse(
    (response) =>
      response.url().includes('/result/confirm/') && response.request().method() === 'POST',
  )
  await panel(page).getByRole('button', { name: '再次确认成绩', exact: true }).click()
  expect((await saved).status()).toBe(200)
  await expect(panel(page)).toHaveCount(0)
}
async function finish(page: Page, id: number) {
  let ws = await read(page, `/tournaments/${id}/workspace/`)
  while (ws.unresolved_groups.length) {
    const members = ws.unresolved_groups[0] as number[]
    await page.getByRole('button', { name: '记录公开抽签 1', exact: true }).click()
    for (const [i, pk] of members.entries())
      await select(
        page,
        `抽签顺位 ${i + 1}`,
        ws.standings.find((row: { participant_id: number }) => row.participant_id === pk)
          .display_name,
      )
    await panel(page).getByLabel('抽签方式', { exact: true }).fill('隔离QA签条')
    await panel(page)
      .getByLabel('实际抽签时间', { exact: true })
      .fill(new Date().toISOString().slice(0, 16))
    await panel(page).getByLabel('公开过程说明', { exact: true }).fill('仅在隔离QA验证新分桌策略。')
    await panel(page).getByRole('button', { name: '保存公开抽签记录' }).click()
    await panel(page).getByRole('button', { name: '二次确认抽签顺序' }).click()
    await expect(panel(page)).toHaveCount(0)
    ws = await read(page, `/tournaments/${id}/workspace/`)
  }
  await page.getByRole('button', { name: '正式完赛', exact: true }).click()
  await panel(page).getByRole('button', { name: '确认完赛并释放本场物理桌' }).click()
  await expect(panel(page)).toHaveCount(0)
  expect((await read(page, `/tournaments/${id}/`)).status).toBe('completed')
}

test('all pairing presets, exact high-table bonuses and manual mouse/keyboard swaps', async ({
  page,
}, info) => {
  await login(page)
  for (const label of [
    '手动拖拽分桌',
    '完全随机',
    '高高碰',
    '瑞士轮 · 避重优先',
    '瑞士轮 · 积分接近优先',
  ]) {
    const id = await create(page, label, 8, 2)
    await openGeneration(page, 1, 2)
    if (label === '手动拖拽分桌') {
      const a = panel(page)
        .getByRole('article', { name: '逻辑桌 A 分组' })
        .locator('[data-pairing-slot]')
        .first()
      const b = panel(page)
        .getByRole('article', { name: '逻辑桌 B 分组' })
        .locator('[data-pairing-slot]')
        .first()
      const aId = await a.getAttribute('data-pair-participant'),
        bId = await b.getAttribute('data-pair-participant')
      const handle = a.locator('[data-pair-handle]')
      await handle.scrollIntoViewIfNeeded()
      const source = await handle.boundingBox(),
        destination = await b.boundingBox()
      await page.mouse.move(source!.x + source!.width / 2, source!.y + source!.height / 2)
      await page.mouse.down()
      await page.mouse.move(destination!.x + destination!.width / 2, destination!.y + 30, {
        steps: 12,
      })
      await page.mouse.up()
      await expect(
        panel(page)
          .getByRole('article', { name: '逻辑桌 A 分组' })
          .locator(`[data-pair-participant="${bId}"]`),
      ).toHaveCount(1)
      await expect(
        panel(page)
          .getByRole('article', { name: '逻辑桌 B 分组' })
          .locator(`[data-pair-participant="${aId}"]`),
      ).toHaveCount(1)
      await page.screenshot({
        path: info.outputPath('manual-mouse-desktop.png'),
        fullPage: false,
        animations: 'disabled',
      })
    }
    const first = await publish(page, id)
    expect(first.tables.map((table: { base_bonus: string }) => table.base_bonus)).toEqual([
      '0',
      '0',
    ])
    await record(page, 1, ['40000', '30000', '20000', '10000'])
    await record(page, 2, ['70000', '10000', '10000', '10000'])
    await openGeneration(page, 2, 2)
    await page.screenshot({
      path: info.outputPath(
        `${label.includes('瑞士') ? (label.endsWith('避重优先') ? 'swiss-repeats' : 'swiss-scores') : label === '高高碰' ? 'ranked' : label === '完全随机' ? 'random' : 'manual'}-round2.png`,
      ),
      fullPage: false,
      animations: 'disabled',
    })
    const second = await publish(page, id)
    if (label === '瑞士轮 · 避重优先')
      expect(second.generation_snapshot.pairing.repeat_pairs).toBe(4)
    if (label === '瑞士轮 · 积分接近优先')
      expect(second.generation_snapshot.pairing.repeat_pairs).toBe(6)
    await record(page, 1, ['40000', '30000', '20000', '10000'])
    await record(page, 2, ['40000', '30000', '20000', '10000'])
    if (label === '高高碰') {
      const rounds = (await read(page, `/tournaments/${id}/rounds/`)).results
      expect(rounds[1].tables.map((table: { base_bonus: string }) => table.base_bonus)).toEqual([
        '5',
        '2',
      ])
      expect(rounds[1].tables[0].result.scores[0].base).toEqual({
        numerator: '15',
        denominator: '1',
      })
      expect(rounds[1].tables[0].result.scores[0].score).toEqual({
        numerator: '65',
        denominator: '1',
      })
    }
    await finish(page, id)
  }
})

test('sixteen-player manual touch drag scrolls from table A to offscreen D on phones', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 900 })
  await login(page)
  const id = await create(page, '手动拖拽分桌', 16, 1)
  await openGeneration(page, 1, 4)
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 })
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    const a = panel(page)
      .getByRole('article', { name: '逻辑桌 A 分组' })
      .locator('[data-pairing-slot]')
      .first()
    const d = panel(page)
      .getByRole('article', { name: '逻辑桌 D 分组' })
      .locator('[data-pairing-slot]')
      .first()
    const aId = await a.getAttribute('data-pair-participant'),
      dId = await d.getAttribute('data-pair-participant')
    const handle = a.locator('[data-pair-handle]')
    await handle.scrollIntoViewIfNeeded()
    const source = await handle.boundingBox()
    const x = source!.x + source!.width / 2,
      y = source!.y + source!.height / 2
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x, y, id: 1 }],
    })
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x, y: 885, id: 1 }],
    })
    await expect
      .poll(
        async () => {
          const box = await d.boundingBox()
          return !!box && box.y + box.height < 850
        },
        { timeout: 15000, intervals: [20] },
      )
      .toBe(true)
    // Move away from the edge to stop scrolling. If the header passed over the
    // first D slot, use the upper edge in this same touch gesture to bring it back.
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x, y: 450, id: 1 }],
    })
    await page.evaluate(
      () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
    )
    if ((await d.boundingBox())!.y < 170) {
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x, y: 160, id: 1 }],
      })
      await expect
        .poll(async () => (await d.boundingBox())!.y > 170, { timeout: 15000, intervals: [20] })
        .toBe(true)
      await cdp.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ x, y: 450, id: 1 }],
      })
      await page.evaluate(
        () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
      )
    }
    const target = await d.boundingBox()
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: target!.x + target!.width / 2, y: target!.y + target!.height / 2, id: 1 }],
    })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await expect(
      panel(page)
        .getByRole('article', { name: '逻辑桌 D 分组' })
        .locator(`[data-pair-participant="${aId}"]`),
    ).toHaveCount(1)
    await expect(
      panel(page)
        .getByRole('article', { name: '逻辑桌 A 分组' })
        .locator(`[data-pair-participant="${dId}"]`),
    ).toHaveCount(1)
    expect(
      await panel(page).evaluate((element) => element.scrollWidth <= element.clientWidth),
    ).toBeTruthy()
    await page.screenshot({
      path: info.outputPath(`manual-touch-${width}.png`),
      fullPage: false,
      animations: 'disabled',
    })
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await publish(page, id)
  for (let table = 1; table <= 4; table++)
    await record(page, table, ['40000', '30000', '20000', '10000'])
  await finish(page, id)
})
