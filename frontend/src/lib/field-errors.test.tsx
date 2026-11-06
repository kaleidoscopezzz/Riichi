// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { formatFieldErrors } from './field-errors'
import { FormFeedback } from '@/components/form-feedback'
import { ApiError } from '@/services/api'

afterEach(cleanup)
describe('DRF 字段错误可读展开', () => {
  it('列表项里的对象按“第 N 项”展开，跳过有效项', () => {
    expect(
      formatFieldErrors({
        points: [{}, { raw_points: ['请填写有效的整数。'] }, {}, {}],
      }),
    ).toEqual(['终局点数：第 2 项：点数：请填写有效的整数。'])
  })

  it('嵌套 dict、ListField 下标、non_field_errors 与多层列表', () => {
    const lines = formatFieldErrors({
      source_versions: [{ table_id: ['桌次不存在。'], version: ['版本必须大于 0。'] }],
      members: { '1': ['请填写有效的整数。'] },
      non_field_errors: ['抽签须准确覆盖一个待决组。'],
      rules: { uma: { '0': ['格式错误。'] }, oka: [['太大。'], ['太小。']] },
      participant_ids: ['同一选手不能重复参赛。', '账号已停用'],
    })
    expect(lines).toEqual([
      '来源成绩版本：第 1 项：桌次：桌次不存在。；成绩版本：版本必须大于 0。',
      '并列组选手：第 2 项：请填写有效的整数。',
      '抽签须准确覆盖一个待决组。',
      'rules：Uma：第 1 项：格式错误。；oka：第 1 项：太大。；第 2 项：太小。',
      '参赛名单：同一选手不能重复参赛。 账号已停用',
    ])
  })

  it('任何形状都不会出现 [object Object]', () => {
    const shapes: unknown[] = [
      { a: { b: { c: { d: ['深层'] } } } },
      { points: [{ raw_points: [{ detail: '嵌套对象' }] }] },
      ['顶层列表', { x: ['对象项'] }],
      '顶层字符串',
      { count: 3, ok: false, empty: null, nothing: undefined, blank: [] },
      { cycle: Array.from({ length: 3 }, () => ({ inner: [{}] })) },
      null,
      42,
    ]
    for (const shape of shapes)
      for (const line of formatFieldErrors(shape)) expect(line).not.toContain('[object')
    expect(formatFieldErrors(['顶层列表', { x: ['对象项'] }])).toEqual([
      '顶层列表；第 2 项：x：对象项',
    ])
    expect(formatFieldErrors({ count: 3, ok: false, empty: null, blank: [] })).toEqual([
      'count：3',
      'ok：false',
    ])
  })

  it('FormFeedback 渲染嵌套字段错误', () => {
    render(
      <FormFeedback
        error={
          new ApiError(400, 'invalid', '输入信息有误，请检查表单。', {
            points: [{}, { raw_points: ['请填写有效的整数。'] }],
            reason: { detail: ['作废原因不能为空。'] },
          })
        }
      />,
    )
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('终局点数：第 2 项：点数：请填写有效的整数。')
    expect(alert.textContent).toContain('原因说明：作废原因不能为空。')
    expect(alert.textContent).not.toContain('[object Object]')
  })
})
