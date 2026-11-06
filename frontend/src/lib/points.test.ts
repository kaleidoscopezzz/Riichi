import { describe, expect, it } from 'vitest'
import { parsePoints } from './points'

describe('终局点数统一解析', () => {
  it.each([
    [' ', null],
    ['\u3000', null], // ideographic (full-width) space
    ['', null],
    ['25000 ', 25000],
    ['\u300025000\u3000', 25000],
    ['２５０００', 25000], // full-width digits
    ['\uFF0D100', -100], // full-width minus
    ['\u2212100', -100], // Unicode minus sign
    ['-0', 0],
    ['0', 0],
    ['9007199254740991', 9007199254740991],
    ['-9007199254740991', -9007199254740991],
  ])('接受 %j → %j', (input, value) => {
    expect(parsePoints(input)).toEqual({ ok: true, value })
  })

  it.each(['1e3', '0x10', '1.5', '+100', '25 000', '1-2', '--1', 'NaN', 'Infinity', '１e３'])(
    '拒绝 %j，给出明确错误而不是 0',
    (input) => {
      const parsed = parsePoints(input)
      expect(parsed.ok).toBe(false)
      if (!parsed.ok) expect(parsed.error).toContain('整数')
    },
  )

  it('超出安全整数范围明确报错', () => {
    for (const input of ['9007199254740992', '-9007199254740993', '99999999999999999999']) {
      const parsed = parsePoints(input)
      expect(parsed).toEqual({ ok: false, error: expect.stringContaining('安全整数范围') })
    }
  })

  it('负零归一为 0，不产生带符号的零', () => {
    const parsed = parsePoints('\uFF0D\uFF10')
    expect(parsed.ok && Object.is(parsed.value, 0)).toBe(true)
  })
})
