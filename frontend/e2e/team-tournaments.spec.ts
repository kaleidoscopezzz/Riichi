import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'

const credentials = JSON.parse(readFileSync(process.env.RIICHI_QA_CREDENTIALS!, 'utf8')) as {
  username: string
  password: string
  prefix: string
}
const dialog = (page: Page) => page.getByRole('dialog')
async function read(page: Page, path: string) {
  const response = await page.request.get('/api/v1' + path)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).data
}
async function select(page: Page, label: string, value: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: value, exact: true }).click()
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
  sizes: number[],
  mode: 'free' | 'positions',
  count: number,
  cycles = 1,
  manual = false,
) {
  await page.goto('/tournaments')
  await page.getByRole('button', { name: '创建团队赛', exact: true }).click()
  const title = `${credentials.prefix} ${mode} ${Date.now()}`
  await dialog(page).getByLabel('赛事名称', { exact: true }).fill(title)
  await select(page, '团队赛程模式', mode === 'free' ? '按整体场次' : '固定位置依次循环')
  if (manual) await select(page, '团队队伍编排', '手动安排四队')
  if (mode === 'free')
    await dialog(page).getByLabel('总桌场次', { exact: true }).fill(String(count))
  else {
    await dialog(page).getByLabel('每位置每队场数', { exact: true }).fill(String(count))
    await dialog(page).getByLabel('循环次数', { exact: true }).fill(String(cycles))
  }
  await select(page, '团队头名赏设置', '自定义（可为 0）')
  await dialog(page).getByLabel('头名赏 Oka', { exact: true }).fill('0')
  while (
    (await dialog(page)
      .getByRole('button', { name: /^移除队伍 / })
      .count()) < sizes.length
  )
    await dialog(page).getByRole('button', { name: '添加队伍', exact: true }).click()
  let player = 1
  for (const [i, size] of sizes.entries()) {
    await dialog(page)
      .getByLabel(`队伍 ${i + 1} 名称`, { exact: true })
      .fill(`${credentials.prefix} 队${i + 1}`)
    for (let j = 0; j < size; j++) {
      const name = `${credentials.prefix} ${String(player++).padStart(2, '0')}`
      await page.getByRole('combobox', { name: `搜索队伍 ${i + 1} 成员`, exact: true }).fill(name)
      await page.getByRole('option').filter({ hasText: name }).click()
    }
  }
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/tournaments/') && r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '保存团队草稿' }).click()
  const response = await saved
  expect(response.status()).toBe(201)
  const row = (await response.json()).data
  await expect(dialog(page)).toHaveCount(0)
  await page.getByRole('button', { name: `查看赛事 ${title}`, exact: true }).click()
  await dialog(page).getByRole('link', { name: '进入团队赛工作台' }).click()
  await expect(page).toHaveURL(new RegExp(`/tournaments/${row.id}/team$`))
  return row
}
async function schedule(page: Page, id: number) {
  await page.getByRole('button', { name: '预览团队赛程', exact: true }).click()
  await dialog(page).getByRole('button', { name: '计算团队赛程预览' }).click()
  await expect(dialog(page).getByRole('heading', { name: '赛程摘要' })).toBeVisible()
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/v1/tournaments/${id}/team/schedule/generate/`) &&
      r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '确认生成团队赛程' }).click()
  expect((await saved).status()).toBe(201)
  await expect(dialog(page)).toHaveCount(0)
}
async function start(page: Page, id: number) {
  await page.getByRole('button', { name: '启动团队赛', exact: true }).click()
  const started = page.waitForResponse((r) => r.url().endsWith(`/api/v1/tournaments/${id}/start/`))
  await dialog(page).getByRole('button', { name: '确认启动团队赛' }).click()
  expect((await started).status()).toBe(200)
  await expect(dialog(page)).toHaveCount(0)
}
async function setFreeLineups(page: Page, tournament: any) {
  const plans = (await read(page, `/tournaments/${tournament.id}/team/plans/`)).results
  for (const p of plans) {
    await page.getByRole('button', { name: `编辑第 ${p.match_number} 场名单`, exact: true }).click()
    for (const teamId of p.team_ids) {
      const team = tournament.teams.find((row: any) => row.id === teamId)
      await select(page, `${team.name} 出场成员`, team.members[0].display_name)
    }
    await dialog(page).getByRole('checkbox', { name: '已收到队长指定名单', exact: true }).check()
    const written = page.waitForResponse(
      (r) => r.url().endsWith(`/team/plans/${p.id}/`) && r.request().method() === 'PUT',
    )
    await dialog(page).getByRole('button', { name: '保存出场计划' }).click()
    expect((await written).status()).toBe(200)
    await expect(dialog(page)).toHaveCount(0)
    const card = page
      .locator('.team-plan-card')
      .filter({ has: page.getByRole('heading', { name: `第 ${p.match_number} 场`, exact: true }) })
    await card.getByRole('button', { name: '确认本场出场', exact: true }).click()
    await dialog(page).getByRole('button', { name: '二次确认本场名单' }).click()
    await expect(dialog(page)).toHaveCount(0)
  }
}
async function batch(page: Page, id: number, first: boolean) {
  await page.getByRole('button', { name: '预览下一开赛时段' }).click()
  if (first) await select(page, '团队逻辑桌 A 物理桌', `800 · ${credentials.prefix} 桌1`)
  await dialog(page).getByRole('button', { name: '计算下一时段预览' }).click()
  await expect(dialog(page).getByRole('heading', { name: /时段 .* 开场确认/ })).toBeVisible()
  const generated = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/v1/tournaments/${id}/team/batches/start/`) &&
      r.request().method() === 'POST',
  )
  await dialog(page).getByRole('button', { name: '确认开场此时段' }).click()
  const response = await generated
  expect(response.status()).toBe(201)
  await expect(dialog(page)).toHaveCount(0)
  return (await response.json()).data
}
async function score(page: Page, row: any, b: any, info?: TestInfo) {
  const teamOf = new Map<number, number>(
    row.teams.flatMap((team: any) => team.members.map((m: any) => [m.participant_id, team.id])),
  )
  const index = new Map<number, number>(row.teams.map((team: any, i: number) => [team.id, i]))
  for (const table of b.tables) {
    await page
      .getByRole('button', {
        name: `录入时段 ${b.round_number} 第${table.table_number}桌成绩`,
        exact: true,
      })
      .click()
    const ids = [...table.seats].sort(
      (a, c) =>
        index.get(teamOf.get(a.participant_id)!)! - index.get(teamOf.get(c.participant_id)!)!,
    )
    for (const [i, seat] of ids.entries())
      await dialog(page)
        .getByLabel(`${seat.display_name} 终局点数`, { exact: true })
        .fill(String([40000, 30000, 20000, 10000][i]))
    if (b.round_number === 1 && info) {
      const firstTeam = row.teams.find((team: any) => team.id === teamOf.get(ids[0].participant_id))
      const contribution = dialog(page).getByLabel(`${firstTeam.name} 累计积分试算`, {
        exact: true,
      })
      await expect(contribution).toBeVisible()
      await expect(contribution.getByTitle('0/1', { exact: true })).toHaveText('0.00')
      await expect(contribution.getByTitle('40/1', { exact: true })).toHaveCount(2)
      await page.screenshot({
        path: info.outputPath('team-live-score-contribution.png'),
        fullPage: false,
      })
    }
    await dialog(page).getByRole('button', { name: '确认成绩', exact: true }).click()
    await dialog(page).getByRole('button', { name: '再次确认成绩', exact: true }).click()
    await expect(dialog(page)).toHaveCount(0)
  }
}
async function confirmTeamLottery(page: Page) {
  // Saving the draw refreshes the dialog; retry against the replacement button
  // instead of letting a single detached node exhaust the test budget.
  for (let attempt = 0; attempt < 30; attempt++) {
    if ((await dialog(page).count()) === 0) return
    try {
      await dialog(page)
        .getByRole('button', { name: '二次确认团队抽签' })
        .click({ timeout: 3000 })
    } catch {
      await page.waitForTimeout(200)
    }
  }
  await expect(dialog(page)).toHaveCount(0)
}
async function finish(page: Page, id: number) {
  let ws = await read(page, `/tournaments/${id}/workspace/`)
  while ((ws.unresolved_groups ?? []).length) {
    const members = ws.unresolved_groups[0]
    await page.getByRole('button', { name: '记录团队公开抽签 1' }).click()
    for (const [i, pk] of members.entries())
      await select(page, `团队抽签顺位 ${i + 1}`, ws.teams.find((team: any) => team.id === pk).name)
    await dialog(page).getByLabel('团队抽签方式', { exact: true }).fill('隔离QA公开纸签')
    await dialog(page)
      .getByLabel('实际团队抽签时间', { exact: true })
      .fill(new Date().toISOString().slice(0, 16))
    await dialog(page)
      .getByLabel('团队公开过程说明', { exact: true })
      .fill('隔离QA真实接口完整记录')
    await dialog(page).getByRole('button', { name: '保存公开团队抽签' }).click()
    await confirmTeamLottery(page)
    await expect(dialog(page)).toHaveCount(0)
    ws = await read(page, `/tournaments/${id}/workspace/`)
  }
  await page.getByRole('button', { name: '正式完赛团队赛' }).click()
  await dialog(page).getByRole('button', { name: '确认团队赛完赛并归档' }).click()
  await expect(dialog(page)).toHaveCount(0)
  await expect(page.getByText('TEAM CHAMPION / 团队冠军')).toBeVisible()
  await page.reload()
  await expect(page.getByText('TEAM CHAMPION / 团队冠军')).toBeVisible()
  await expect(page.getByRole('button', { name: '预览下一开赛时段' })).toHaveCount(0)
  return read(page, `/tournaments/${id}/workspace/`)
}
async function theme(page: Page, value: string) {
  if (
    ((await page.locator('html').getAttribute('class'))?.includes('dark') ? 'dark' : 'light') !==
    value
  )
    await page.getByRole('button', { name: /切换为.*主题/ }).click()
}

test('six variable teams and twenty-four members complete free matches with real team contributions and responsive themes', async ({
  page,
}, info) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await login(page)
  const t = await create(page, [1, 7, 2, 5, 6, 3], 'free', 6)
  expect(t.participant_count).toBe(24)
  expect(t.round_count).toBeNull()
  await schedule(page, t.id)
  await setFreeLineups(page, t)
  await start(page, t.id)
  for (let i = 0; i < 6; i++) {
    const b = await batch(page, t.id, i === 0)
    await score(page, t, b, info)
  }
  const result = await finish(page, t.id)
  expect(result.team_standings).toHaveLength(6)
  expect(result.team_standings.every((team: any) => team.confirmed_matches === 4)).toBeTruthy()
  expect(result.champion_id).toBeNull()
  expect(result.champion_team_id).toBeTruthy()
  await page.locator('.team-standings-scroll tbody tr').first().getByText('展开本队贡献').click()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const value of ['light', 'dark']) {
      await theme(page, value)
      expect(await page.locator('body').evaluate((el) => el.scrollWidth <= innerWidth)).toBeTruthy()
      await page.screenshot({
        path: info.outputPath(`team-free-${width}-${value}.png`),
        fullPage: true,
        animations: 'disabled',
      })
    }
  }
  expect(errors).toEqual([])
  writeFileSync(
    info.outputPath('free-team-summary.json'),
    JSON.stringify(
      {
        id: t.id,
        teams: 6,
        members: 24,
        matches: 6,
        champion_team_id: result.champion_team_id,
        per_team: result.team_standings.map((team: any) => ({
          team_id: team.team_id,
          total: team.total,
          games: team.confirmed_matches,
        })),
        page_errors: errors,
      },
      null,
      2,
    ),
  )
})

test('two cycles of five positions finish twenty matches, allow next-cycle substitutes and retain fixed representatives', async ({
  page,
}, info) => {
  await login(page)
  const t = await create(page, [2, 2, 2, 2], 'positions', 2, 2)
  await schedule(page, t.id)
  await start(page, t.id)
  const stages = (await read(page, `/tournaments/${t.id}/workspace/`)).stages
  let count = 0
  for (const stage of stages) {
    await page.getByRole('button', { name: '编辑本位置代表名单', exact: true }).click()
    for (const team of t.teams)
      await select(
        page,
        `${team.name} ${stage.position_label}代表`,
        team.members[stage.cycle - 1].display_name,
      )
    if (count === 0) {
      await page
        .getByRole('combobox', {
          name: `${t.teams[0].name} ${stage.position_label}代表`,
          exact: true,
        })
        .click()
      await page.screenshot({
        path: info.outputPath('team-representative-select.png'),
        fullPage: false,
      })
      await page.keyboard.press('Escape')
    }
    await dialog(page).getByRole('button', { name: '保存位置代表名单' }).click()
    await expect(dialog(page)).toHaveCount(0)
    await page.getByRole('button', { name: '预览确认本位置计划' }).click()
    await dialog(page).getByRole('button', { name: '二次确认本位置全部名单' }).click()
    await expect(dialog(page)).toHaveCount(0)
    for (let i = 0; i < 2; i++) {
      const b = await batch(page, t.id, count === 0)
      await score(page, t, b)
      count++
    }
  }
  const result = await finish(page, t.id)
  expect(count).toBe(20)
  expect(result.match_count).toBe(20)
  const batches = await read(page, `/tournaments/${t.id}/team/batches/`)
  expect(batches.count).toBe(20)
  expect(result.team_standings.every((team: any) => team.confirmed_matches === 20)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('team-positions-completed.png'), fullPage: true })
  writeFileSync(
    info.outputPath('position-team-summary.json'),
    JSON.stringify({
      id: t.id,
      stages: stages.map((s: any) => ({ cycle: s.cycle, role: s.position_label })),
      matches: count,
      batches: batches.count,
      champion_team_id: result.champion_team_id,
    }),
  )
})

test('odd team stage validation explains the seats, preserves configuration and accepts four matches', async ({
  page,
}, info) => {
  await login(page)
  const t = await create(page, [1, 1, 1, 1, 1], 'positions', 2)
  await page.getByRole('button', { name: '预览团队赛程' }).click()
  await dialog(page).getByRole('button', { name: '计算团队赛程预览' }).click()
  await expect(dialog(page).getByRole('alert')).toContainText('10个席位')
  expect((await read(page, `/tournaments/${t.id}/`)).team_settings.games_per_position).toBe(2)
  await page.screenshot({
    path: info.outputPath('team-five-invalid-two-games.png'),
    fullPage: false,
  })
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '编辑团队草稿' }).click()
  await dialog(page).getByLabel('每位置每队场数', { exact: true }).fill('4')
  await dialog(page).getByRole('button', { name: '保存团队草稿' }).click()
  await expect(dialog(page)).toHaveCount(0)
  await schedule(page, t.id)
  expect((await read(page, `/tournaments/${t.id}/team/plans/`)).count).toBe(25)
})

test('team editor strategy and schedule selects expand without viewport overflow in phone light and dark themes', async ({
  page,
}, info) => {
  await login(page)
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const value of ['light', 'dark']) {
      await theme(page, value)
      await page.goto('/tournaments')
      await page.getByRole('button', { name: '创建团队赛', exact: true }).click()
      await page.getByRole('combobox', { name: '团队赛程模式', exact: true }).click()
      await expect(page.getByRole('option')).toHaveCount(2)
      expect(
        await page.getByRole('listbox').evaluate((el) => {
          const box = el.getBoundingClientRect()
          return box.left >= 0 && box.right <= innerWidth
        }),
      ).toBeTruthy()
      await page.screenshot({
        path: info.outputPath(`team-mode-select-${width}-${value}.png`),
        fullPage: false,
      })
      await page.keyboard.press('Escape')
      await page.keyboard.press('Escape')
      await expect(dialog(page)).toHaveCount(0)
    }
  }
})

test('manual fixed-position groups can swap teams through the UI while keeping captain representatives and equal stage quotas', async ({
  page,
}, info) => {
  await login(page)
  const t = await create(page, [1, 1, 1, 1, 1], 'positions', 4, 1, true)
  await schedule(page, t.id)
  const stage = (await read(page, `/tournaments/${t.id}/workspace/`)).stages[0]
  await page.getByRole('button', { name: '编辑本位置代表名单', exact: true }).click()
  for (const team of t.teams)
    await select(page, `${team.name} ${stage.position_label}代表`, team.members[0].display_name)
  await dialog(page).getByRole('button', { name: '保存位置代表名单' }).click()
  await expect(dialog(page)).toHaveCount(0)
  const plans = (await read(page, `/tournaments/${t.id}/team/plans/?stage=${stage.id}`)).results
  const [first, second] = plans
  const missingFirst = t.teams.find((team: any) => !first.team_ids.includes(team.id))
  const missingSecond = t.teams.find((team: any) => !second.team_ids.includes(team.id))
  for (const [p, removed, replacement] of [
    [first, missingSecond, missingFirst],
    [second, missingFirst, missingSecond],
  ]) {
    await page.getByRole('button', { name: `编辑第 ${p.match_number} 场四队`, exact: true }).click()
    await expect(dialog(page).getByRole('button', { name: '保存四队分组' })).toBeVisible()
    await expect(dialog(page).getByText('本场只调整四队分组', { exact: false })).toBeVisible()
    await expect(dialog(page).getByRole('combobox', { name: /出场成员/ })).toHaveCount(0)
    await select(page, `参赛队伍 ${p.team_ids.indexOf(removed.id) + 1}`, replacement.name)
    const saved = page.waitForResponse(
      (r) => r.url().endsWith(`/team/plans/${p.id}/`) && r.request().method() === 'PUT',
    )
    await dialog(page).getByRole('button', { name: '保存四队分组' }).click()
    const response = await saved
    expect(response.status()).toBe(200)
    expect(response.request().postDataJSON()).not.toHaveProperty('lineup')
    const updated = (await response.json()).data
    expect(updated.lineup[String(replacement.id)]).toBe(replacement.members[0].id)
    expect(updated.captain_supplied).toBeTruthy()
    await expect(dialog(page)).toHaveCount(0)
  }
  await page.getByRole('button', { name: '预览确认本位置计划' }).click()
  await dialog(page).getByRole('button', { name: '二次确认本位置全部名单' }).click()
  await expect(dialog(page)).toHaveCount(0)
  const updatedPlans = (await read(page, `/tournaments/${t.id}/team/plans/?stage=${stage.id}`))
    .results
  for (const team of t.teams)
    expect(updatedPlans.filter((p: any) => p.team_ids.includes(team.id))).toHaveLength(4)
  expect(updatedPlans.every((p: any) => p.status === 'confirmed')).toBeTruthy()
  await page.screenshot({
    path: info.outputPath('team-manual-position-groups.png'),
    fullPage: true,
  })
})
