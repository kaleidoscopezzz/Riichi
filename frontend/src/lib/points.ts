export type PointsParse = { ok: true; value: number | null } | { ok: false; error: string }

// Leading/trailing blanks, including the ideographic (full-width) space and BOM.
const edgeBlanks = /^[\s\u3000\uFEFF]+|[\s\u3000\uFEFF]+$/g
// Full-width digits ０-９.
const fullWidthDigits = /[\uFF10-\uFF19]/g
// Full-width hyphen-minus "－" and the Unicode minus sign "−".
const minusSigns = /[\uFF0D\u2212]/g

/**
 * The single parser for raw table points, shared by draft save, the running total
 * and the confirmation check. An empty field is `null` (allowed in a draft only);
 * anything which is not a plain safe integer is an explicit error, never 0.
 */
export function parsePoints(input: string): PointsParse {
  const text = input
    .replace(edgeBlanks, '')
    .replace(fullWidthDigits, (digit) => String.fromCharCode(digit.charCodeAt(0) - 0xfee0))
    .replace(minusSigns, '-')
  if (!text) return { ok: true, value: null }
  if (!/^-?\d+$/.test(text))
    return { ok: false, error: '只能填写整数（可带负号），不支持小数、指数、十六进制或其他字符。' }
  const value = Number(text)
  if (!Number.isSafeInteger(value))
    return { ok: false, error: '超出安全整数范围（±9007199254740991）。' }
  // Normalise -0 so drafts and totals never carry a signed zero.
  return { ok: true, value: value === 0 ? 0 : value }
}
