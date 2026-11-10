import { expect, test, type Page } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'

const credentials = JSON.parse(readFileSync(process.env.RIICHI_QA_CREDENTIALS!, 'utf8')) as {
  username: string
  password: string
  prefix: string
  existing_swiss_ids: Record<string, number>
}
const dialog = (page: Page) => page.getByRole('dialog')
async function read(page: Page, path: string) {
  const response = await page.request.get('/api/v1' + path)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).data
}
async function write(page: Page, path: string, data: unknown, method = 'POST') {
  const csrf = (await read(page, '/auth/csrf/')).csrf_token
  return page.request.fetch('/api/v1' + path, {
    method,
    data,
    headers: { 'X-CSRFToken': csrf, Origin: new URL(page.url()).origin },
  })
}
async function select(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: option, exact: true }).click()
}
async function login(page: Page) {
  await page.goto('/tournaments')
  await page.getByLabel('用户名', { exact: true }).fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/tournaments$/)
}
async function create(
  page: Page,
  title: string,
  size: number,
  rounds: number,
  strategy = '高高碰',
) {
  await page.goto('/tournaments')
  await page.getByRole('button', { name: '创建赛事', exact: true }).click()
  const name = `${credentials.prefix} ${title} ${Date.now()}`
  await dialog(page).getByLabel('赛事名称', { exact: true }).fill(name)
  await select(page, '总轮数', `${rounds} 轮`)
  await select(page, '分桌策略', strategy)
  await select(page, '头名赏设置', '自定义（可为 0）')
  await dialog(page).getByLabel('头名赏 Oka', { exact: true }).fill('0')
  if (strategy === '高高碰') {
    for (const [i, value] of ['5', '2', '1', '0'].entries())
      await dialog(page).getByLabel(`${'ABCD'[i]}桌附加基础分`).fill(value)
  }
  for (let i = 0; i < size; i++) {
    const player = `${credentials.prefix} ${String(i + 1).padStart(2, '0')}`
    await page.getByRole('combobox', { name: '搜索参赛选手' }).fill(player)
    await page.getByRole('option').filter({ hasText: player }).click()
  }
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/tournaments/') && r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '保存草稿', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(201)
  const id = (await response.json()).data.id as number
  await expect(dialog(page)).toHaveCount(0)
  await page.getByRole('button', { name: `查看赛事 ${name}`, exact: true }).click()
  await dialog(page).getByRole('button', { name: '启动前检查' }).click()
  await dialog(page).getByRole('button', { name: '确认启动并冻结' }).click()
  await expect(dialog(page)).toHaveCount(0)
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
  await expect(dialog(page).getByRole('article', { name: '逻辑桌 A 分组' })).toBeVisible()
  await dialog(page).getByRole('button', { name: '预览并确认', exact: true }).click()
}
async function generate(page: Page, id: number, number: number, tables: number) {
  await openGeneration(page, number, tables)
  const request = page.waitForResponse(
    (r) => r.url().endsWith(`/api/v1/tournaments/${id}/rounds/`) && r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '确认生成轮次', exact: true }).click()
  const response = await request
  expect(response.status()).toBe(201)
  await expect(dialog(page)).toHaveCount(0)
  return (await response.json()).data
}
async function record(page: Page, table: number, points: number[]) {
  await page.getByRole('button', { name: `录入第${table}桌成绩`, exact: true }).click()
  const fields = dialog(page).getByRole('textbox', { name: /终局点数$/ })
  for (const [i, value] of points.entries()) await fields.nth(i).fill(String(value))
  await dialog(page).getByRole('button', { name: '确认成绩', exact: true }).click()
  const request = page.waitForResponse(
    (r) => r.url().includes('/result/confirm/') && r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '再次确认成绩', exact: true }).click()
  expect((await request).status()).toBe(200)
  await expect(dialog(page)).toHaveCount(0)
}
async function recordUnique(page: Page, round: number, tables: number) {
  for (let table = 1; table <= tables; table++) {
    const adjustment = round * 101 + table * 13
    await record(page, table, [
      40000 + adjustment,
      30000 + 2 * adjustment,
      20000 - adjustment,
      10000 - 2 * adjustment,
    ])
  }
}
async function enterDraw(page: Page, workspace: any, members: number[]) {
  for (const [index, pk] of members.entries())
    await select(
      page,
      `抽签顺位 ${index + 1}`,
      workspace.standings.find((row: any) => row.participant_id === pk).display_name,
    )
  await dialog(page).getByLabel('抽签方式', { exact: true }).fill('隔离QA公开纸签')
  await dialog(page)
    .getByLabel('实际抽签时间', { exact: true })
    .fill(new Date().toISOString().slice(0, 16))
  await dialog(page)
    .getByLabel('公开过程说明', { exact: true })
    .fill('仅隔离QA验证公开抽签，顺序靠前者优先。')
  await dialog(page).getByRole('button', { name: '保存公开抽签记录' }).click()
  await expect(dialog(page).getByRole('heading', { name: /待二次确认的抽签记录/ })).toBeVisible()
}
async function finish(page: Page, id: number) {
  let workspace = await read(page, `/tournaments/${id}/workspace/`)
  while ((workspace.unresolved_groups ?? []).length) {
    await page.getByRole('button', { name: '记录公开抽签 1', exact: true }).click()
    await enterDraw(page, workspace, workspace.unresolved_groups[0])
    await dialog(page).getByRole('button', { name: '二次确认抽签顺序' }).click()
    await expect(dialog(page)).toHaveCount(0)
    workspace = await read(page, `/tournaments/${id}/workspace/`)
  }
  await page.getByRole('button', { name: '正式完赛', exact: true }).click()
  await dialog(page).getByRole('button', { name: '确认完赛并释放本场物理桌' }).click()
  await expect(dialog(page)).toHaveCount(0)
  return read(page, `/tournaments/${id}/workspace/`)
}
async function theme(page: Page, value: string) {
  const current = (await page.locator('html').getAttribute('class'))?.includes('dark')
    ? 'dark'
    : 'light'
  if (current !== value) await page.getByRole('button', { name: /切换为.*主题/ }).click()
}
async function eliminate(page: Page, id: number) {
  await page.getByRole('button', { name: '预览淘汰末四人', exact: true }).click()
  await expect(dialog(page).getByLabel('待淘汰四人').getByRole('listitem')).toHaveCount(4)
  const request = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/v1/tournaments/${id}/eliminations/`) &&
      r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '确认淘汰这四人' }).click()
  const response = await request
  expect(response.status()).toBe(201)
  const body = response.request().postDataJSON()
  expect(body.participant_ids).toHaveLength(4)
  expect(body.participant_statuses).toHaveLength(16)
  await expect(dialog(page)).toHaveCount(0)
  return (await response.json()).data
}

test('monthly and daily events share a machine; maintenance blocks next round until explicit replacement', async ({
  page,
}, info) => {
  await login(page)
  const monthly = await create(page, '月度共享', 8, 2)
  await generate(page, monthly, 1, 2)
  const daily = await create(page, '当日共享', 4, 1, '完全随机')
  await generate(page, daily, 1, 1)
  const resources = (await read(page, '/machine-resources/')).results
  const machine = resources.find((row: any) => row.machine_no === '800')
  expect(machine.assignable).toBe(true)
  expect(
    machine.reservations.map((row: any) => row.tournament_id).sort((a: number, b: number) => a - b),
  ).toEqual([monthly, daily])
  await recordUnique(page, 1, 1)
  const dailyResult = await finish(page, daily)
  expect(dailyResult.status).toBe('completed')
  expect(
    (await read(page, '/machine-resources/')).results
      .find((row: any) => row.machine_id === machine.machine_id)
      .reservations.map((row: any) => row.tournament_id),
  ).toEqual([monthly])
  await page.goto(`/tournaments/${monthly}/rounds`)
  await recordUnique(page, 1, 2)
  expect(
    (
      await write(page, `/machines/${machine.machine_id}/`, { status: 'maintenance' }, 'PATCH')
    ).status(),
  ).toBe(200)
  try {
    await page.reload()
    await openGeneration(page, 2, 2)
    const rejected = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/api/v1/tournaments/${monthly}/rounds/`) &&
        r.request().method() === 'POST',
    )
    await dialog(page).getByRole('button', { name: '确认生成轮次' }).click()
    expect((await rejected).status()).toBe(409)
    await expect(dialog(page).getByRole('alert')).toContainText('固定物理桌不可用')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '故障换桌' }).first().click()
    await select(page, '目标可用物理桌', `803 · ${credentials.prefix} 桌4`)
    await dialog(page).getByLabel('故障及替换原因').fill('本轮QA维护替换')
    await dialog(page).getByRole('button', { name: '预览替换' }).click()
    await dialog(page).getByRole('button', { name: '确认故障替换' }).click()
    await expect(dialog(page)).toHaveCount(0)
    const second = await generate(page, monthly, 2, 2)
    expect(second.tables[0].machine_snapshot.machine_no).toBe('803')
    const rounds = (await read(page, `/tournaments/${monthly}/rounds/`)).results
    expect(rounds[0].tables[0].machine_snapshot.machine_no).toBe('800')
  } finally {
    expect(
      (
        await write(page, `/machines/${machine.machine_id}/`, { status: 'available' }, 'PATCH')
      ).status(),
    ).toBe(200)
  }
  await recordUnique(page, 2, 2)
  await finish(page, monthly)
  writeFileSync(
    info.outputPath('shared-machines-summary.json'),
    JSON.stringify({
      monthly,
      daily,
      shared: true,
      maintenance_blocked: true,
      old_snapshot_preserved: true,
    }),
  )
})

test('sixteen players finish six configured rounds with optional elimination and readable statistics in both themes', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await login(page)
  const id = await create(page, '十六人可选淘汰', 16, 6)
  const sizes = [16, 16, 12, 12, 8, 4]
  const eliminationRounds: number[] = []
  for (let number = 1; number <= 6; number++) {
    const round = await generate(page, id, number, sizes[number - 1] / 4)
    expect(round.tables.flatMap((table: any) => table.seats)).toHaveLength(sizes[number - 1])
    await recordUnique(page, number, sizes[number - 1] / 4)
    if ([2, 4, 5].includes(number)) {
      const workspace = await read(page, `/tournaments/${id}/workspace/`)
      expect(workspace.elimination.ready).toBe(true)
      if (number === 2) {
        await theme(page, 'light')
        await page.getByRole('button', { name: '预览淘汰末四人' }).click()
        await page.screenshot({
          path: info.outputPath('elimination-preview-desktop-light.png'),
          fullPage: false,
          animations: 'disabled',
        })
        await page.keyboard.press('Escape')
        expect((await read(page, `/tournaments/${id}/workspace/`)).eliminations).toHaveLength(0)
        await theme(page, 'dark')
        await page.getByRole('button', { name: '预览淘汰末四人' }).click()
        await page.screenshot({
          path: info.outputPath('elimination-preview-desktop-dark.png'),
          fullPage: false,
          animations: 'disabled',
        })
        await page.keyboard.press('Escape')
      }
      await eliminate(page, id)
      eliminationRounds.push(number)
      if (number === 5) {
        const resources = (await read(page, '/machine-resources/')).results
        const machine = resources.find((row: any) => row.machine_no === '800')
        expect(
          (
            await write(
              page,
              `/machines/${machine.machine_id}/`,
              { status: 'maintenance' },
              'PATCH',
            )
          ).status(),
        ).toBe(200)
        try {
          await page.getByRole('button', { name: '故障换桌' }).first().click()
          await select(page, '目标可用物理桌', `803 · ${credentials.prefix} 桌4`)
          await dialog(page).getByLabel('故障及替换原因').fill('淘汰后复用本赛事空桌，无需额外设备')
          await dialog(page).getByRole('button', { name: '预览替换' }).click()
          await dialog(page).getByRole('button', { name: '确认故障替换' }).click()
          await expect(dialog(page)).toHaveCount(0)
        } finally {
          expect(
            (
              await write(
                page,
                `/machines/${machine.machine_id}/`,
                { status: 'available' },
                'PATCH',
              )
            ).status(),
          ).toBe(200)
        }
      }
    }
  }
  await expect(page.getByRole('button', { name: '预览淘汰末四人' })).toHaveCount(0)
  const final = await finish(page, id)
  expect(final.standings).toHaveLength(16)
  expect(final.eliminations.map((row: any) => row.round_number)).toEqual([2, 4, 5])
  const finalRounds = (await read(page, `/tournaments/${id}/rounds/`)).results
  expect(finalRounds[5].tables[0].machine_snapshot.machine_no).toBe('803')
  expect(finalRounds[4].tables[0].machine_snapshot.machine_no).toBe('800')
  expect(
    final.standings.slice(0, 4).every((row: any) => row.eliminated_after_round === null),
  ).toBeTruthy()
  expect(final.standings.map((row: any) => row.rank)).toEqual(
    Array.from({ length: 16 }, (_, i) => i + 1),
  )
  await expect(page.getByLabel('本场成绩亮点')).toBeVisible()
  await page
    .locator('.standings-scroll tbody tr')
    .first()
    .getByText(/展开 .*轮成绩/)
    .click()
  await page.locator('.standings-scroll tbody tr').first().getByText('查看精确值').first().click()
  await expect(page.getByRole('columnheader', { name: '每轮成绩明细' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '第一 / 第二' })).toHaveCount(0)
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const value of ['light', 'dark']) {
      await theme(page, value)
      expect(
        await page.locator('body').evaluate((el) => el.scrollWidth <= window.innerWidth),
      ).toBeTruthy()
      await expect(page.getByRole('table')).toHaveCount(1)
      if (width < 700) {
        expect(
          await page
            .locator('.round-score-card')
            .first()
            .evaluate((el) => {
              const box = el.getBoundingClientRect()
              return box.left >= 0 && box.right <= window.innerWidth
            }),
        ).toBeTruthy()
      }
      await page.screenshot({
        path: info.outputPath(`statistics-rounds-${width}-${value}.png`),
        fullPage: true,
        animations: 'disabled',
      })
    }
  }
  expect(errors).toEqual([])
  writeFileSync(
    info.outputPath('six-round-elimination-summary.json'),
    JSON.stringify(
      {
        id,
        sizes,
        eliminationRounds,
        ranks: final.standings.map((row: any) => row.rank),
        statistics: final.statistics,
        page_errors: errors,
      },
      null,
      2,
    ),
  )
})

test('a tied elimination boundary requires a public draw; later correction preserves eligibility and generated seats', async ({
  page,
}, info) => {
  await login(page)
  const id = await create(page, '淘汰边界并列', 8, 2, '完全随机')
  const first = await generate(page, id, 1, 2)
  await record(page, 1, [25000, 25000, 25000, 25000])
  await record(page, 2, [25000, 25000, 25000, 25000])
  const workspace = await read(page, `/tournaments/${id}/workspace/`)
  expect(workspace.elimination.ready).toBe(false)
  await expect(page.getByRole('button', { name: '预览淘汰末四人' })).toBeDisabled()
  const members = [...workspace.elimination.unresolved_groups[0]].reverse() as number[]
  const rejected = await write(page, `/tournaments/${id}/eliminations/`, {
    round_number: 1,
    source_versions: workspace.source_versions,
    participant_statuses: workspace.participant_statuses,
    participant_ids: members.slice(-4),
    confirmed: true,
  })
  expect(rejected.status()).toBe(409)
  expect((await rejected.json()).error.code).toBe('elimination_lottery_required')
  await page.getByRole('button', { name: '记录淘汰边界公开抽签' }).click()
  await enterDraw(page, workspace, members)
  expect(
    (await read(page, `/tournaments/${id}/workspace/`)).standings.every(
      (row: any) => row.eliminated_after_round === null,
    ),
  ).toBeTruthy()
  await dialog(page).getByRole('button', { name: '取消', exact: true }).click()
  await page.reload()
  await page.getByRole('button', { name: '记录淘汰边界公开抽签' }).click()
  await expect(dialog(page).getByRole('button', { name: '保存公开抽签记录' })).toHaveCount(0)
  await dialog(page).getByRole('button', { name: '二次确认抽签顺序' }).click()
  await expect(dialog(page)).toHaveCount(0)
  await page.getByRole('button', { name: '预览淘汰末四人' }).click()
  await dialog(page).getByRole('button', { name: '确认淘汰这四人' }).click()
  await expect(dialog(page)).toHaveCount(0)
  const eliminated = (await read(page, `/tournaments/${id}/workspace/`)).eliminations[0]
    .participant_ids as number[]
  expect(eliminated).toEqual(members.slice(-4))
  const second = await generate(page, id, 2, 1)
  const secondSeats = second.tables[0].seats.map((row: any) => row.participant_id)
  expect(secondSeats.some((pk: number) => eliminated.includes(pk))).toBeFalsy()
  await select(page, '查看轮次', '第 1 轮')
  const oldTable = first.tables.find((table: any) =>
    table.seats.some((seat: any) => seat.participant_id === eliminated[0]),
  )
  await page
    .getByRole('button', { name: `更正第1轮第${oldTable.table_number}桌成绩`, exact: true })
    .click()
  const others = [30000, 20000, -850000]
  for (const seat of oldTable.seats) {
    const value = seat.participant_id === eliminated[0] ? 900000 : others.shift()!
    await dialog(page)
      .getByLabel(`${seat.display_name} 终局点数`, { exact: true })
      .fill(String(value))
  }
  await expect(dialog(page).getByLabel('实时积分试算')).toContainText('900000')
  const corrected = page.waitForResponse(
    (r) => r.url().includes('/result/correct/') && r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '保存更正' }).click()
  expect((await corrected).status()).toBe(200)
  await expect(dialog(page)).toHaveCount(0)
  const current = await read(page, `/tournaments/${id}/workspace/`)
  expect(
    current.standings.find((row: any) => row.participant_id === eliminated[0])
      .eliminated_after_round,
  ).toBe(1)
  expect(
    (await read(page, `/tournaments/${id}/rounds/`)).results[1].tables[0].seats.map(
      (row: any) => row.participant_id,
    ),
  ).toEqual(secondSeats)
  await select(page, '查看轮次', '第 2 轮')
  await recordUnique(page, 2, 1)
  const final = await finish(page, id)
  expect(eliminated).not.toContain(final.champion_id)
  expect(final.statistics.highest_raw_points.value).toBe(900000)
  expect(final.statistics.highest_raw_points.participant_ids).toContain(eliminated[0])
  writeFileSync(
    info.outputPath('boundary-correction-summary.json'),
    JSON.stringify({
      id,
      eliminated,
      champion_id: final.champion_id,
      generated_seats_preserved: true,
      correction_keeps_eligibility: true,
    }),
  )
})

test('three new strategies and existing Swiss labels use the shared Select in desktop and phone themes', async ({
  page,
}, info) => {
  await login(page)
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const value of ['light', 'dark']) {
      await theme(page, value)
      await page.goto('/tournaments')
      await page.getByRole('button', { name: '创建赛事', exact: true }).click()
      await page.getByRole('combobox', { name: '分桌策略', exact: true }).click()
      await expect(page.getByRole('option')).toHaveCount(3)
      expect(await page.getByRole('option').allTextContents()).toEqual([
        '高高碰',
        '完全随机',
        '手动拖拽分桌',
      ])
      expect(
        await page
          .getByRole('listbox')
          .evaluate(
            (el) =>
              el.getBoundingClientRect().right <= window.innerWidth &&
              el.getBoundingClientRect().left >= 0,
          ),
      ).toBeTruthy()
      await page.screenshot({
        path: info.outputPath(`strategy-select-${width}-${value}.png`),
        fullPage: false,
        animations: 'disabled',
      })
      await page.keyboard.press('Escape')
      await page.keyboard.press('Escape')
      await expect(dialog(page)).toHaveCount(0)
    }
  }
  const old = await read(
    page,
    `/tournaments/${credentials.existing_swiss_ids.swiss_repeats_first_v1}/`,
  )
  await page.goto('/tournaments')
  await page.getByLabel('搜索赛事名称').fill(old.name)
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByRole('button', { name: `查看赛事 ${old.name}`, exact: true }).click()
  await expect(
    dialog(page).getByText('瑞士轮 · 避重优先（既有赛事）', { exact: true }),
  ).toBeVisible()
  await expect(dialog(page).locator('select:not([aria-hidden="true"])')).toHaveCount(0)
})
