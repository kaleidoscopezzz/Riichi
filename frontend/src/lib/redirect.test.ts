import { describe, expect, it } from 'vitest'
import { safeReturnPath } from './redirect'

describe('登录后回跳地址只允许站内路径', () => {
  it.each([
    ['/players', '/players'],
    ['/tournaments/5/rounds', '/tournaments/5/rounds'],
    ['/players?search=abc#list', '/players?search=abc#list'],
    [
      { pathname: '/machines', search: '?status=available', hash: '#top' },
      '/machines?status=available#top',
    ],
    [{ pathname: '/players' }, '/players'],
    ['/', '/'],
  ])('保留站内地址 %j', (from, expected) => {
    expect(safeReturnPath(from)).toBe(expected)
  })

  it.each([
    undefined,
    null,
    '',
    42,
    {},
    { pathname: 42 },
    'players',
    '//evil.example/players',
    'https://evil.example/players',
    'javascript:alert(1)',
    '/\\evil.example',
    '/\t/evil.example',
    '/\n/evil.example',
    '/login',
    '/login/',
    '/LOGIN?next=/players',
    '/register',
    { pathname: '/login', search: '', hash: '' },
    { pathname: '//evil.example', search: '', hash: '' },
    '/players/../login',
    '/players/%2e%2e/register',
  ])('拒绝 %j 并回到仪表盘', (from) => {
    expect(safeReturnPath(from)).toBe('/dashboard')
  })
})
