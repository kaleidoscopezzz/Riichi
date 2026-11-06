const labels: Record<string, string> = {
  username: '用户名',
  nickname: '选手昵称',
  password: '密码',
  password_confirm: '确认密码',
  machine_no: '设备编号',
  name: '名称',
  location: '设备位置',
  description: '备注',
  status: '状态',
  round_count: '总轮数',
  starting_points: '开局点数',
  return_points: '返还原点',
  uma: 'Uma',
  participant_ids: '参赛名单',
  round_number: '轮次',
  machine_id: '物理设备',
  machine_ids: '物理桌',
  reason: '原因说明',
  points: '终局点数',
  raw_points: '点数',
  participant_id: '参赛选手',
  version: '成绩版本',
  source_versions: '来源成绩版本',
  table_id: '桌次',
  members: '并列组选手',
  order: '抽签顺序',
  method: '抽签方式',
  drawn_at: '抽签时间',
  historical_only: '历史补录',
  ordinal: '逻辑桌',
  confirmed: '二次确认',
  revision: '草稿版本',
}
// DRF keys whose messages read better without a field prefix.
const unlabeled = new Set(['non_field_errors', 'detail'])
const maxDepth = 8

const isNested = (value: unknown) => value !== null && typeof value === 'object'

// DRF reports ListField child errors as a dict keyed by zero-based index.
const label = (key: string) => (/^\d+$/.test(key) ? `第 ${Number(key) + 1} 项` : labels[key] || key)

function entry(key: string, value: unknown, depth: number) {
  const text = describe(value, depth)
  if (!text) return ''
  return unlabeled.has(key) ? text : `${label(key)}：${text}`
}

function describe(value: unknown, depth: number): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint')
    return String(value)
  if (typeof value !== 'object' || depth > maxDepth) return ''
  if (Array.isArray(value)) {
    // Many=True serializers report one entry per list item, `{}` for valid ones.
    const nested = value.some(isNested)
    return value
      .map((item, index) => {
        const text = describe(item, depth + 1)
        return text && isNested(item) ? `第 ${index + 1} 项：${text}` : text
      })
      .filter(Boolean)
      .join(nested ? '；' : ' ')
  }
  return Object.entries(value)
    .map(([key, item]) => entry(key, item, depth + 1))
    .filter(Boolean)
    .join('；')
}

/**
 * Flatten DRF validation errors (lists, nested dicts, per-item lists) into readable
 * Chinese lines, one per top-level field. Never yields "[object Object]".
 */
export function formatFieldErrors(fields: unknown): string[] {
  if (!isNested(fields) || Array.isArray(fields)) {
    const text = describe(fields, 0)
    return text ? [text] : []
  }
  return Object.entries(fields as Record<string, unknown>)
    .map(([key, value]) => entry(key, value, 1))
    .filter(Boolean)
}
