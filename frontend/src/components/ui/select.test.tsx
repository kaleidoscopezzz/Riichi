// @vitest-environment jsdom
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Select } from './select'
import { Sheet, SheetContent, SheetTitle, SheetDescription } from './sheet'

afterEach(cleanup)
const options = [
  { value: '', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'disabled', label: '停用项', disabled: true },
  { value: 'started', label: '已启动' },
]
function Field({ changed = () => {} }: { changed?: (value: string) => void }) {
  const [value, setValue] = useState('draft')
  return (
    <Select
      aria-label="赛事状态"
      value={value}
      options={options}
      onValueChange={(v) => {
        setValue(v)
        changed(v)
      }}
    />
  )
}

describe('统一 Radix Select', () => {
  it('真实应用 listbox Portal 展开，鼠标选择并恢复触发器焦点', async () => {
    const changed = vi.fn(),
      user = userEvent.setup()
    const { container } = render(<Field changed={changed} />)
    const trigger = screen.getByRole('combobox', { name: '赛事状态' })
    await user.click(trigger)
    const menu = screen.getByRole('listbox')
    expect(container.contains(menu)).toBe(false)
    expect(screen.getByRole('option', { name: '草稿' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('option', { name: '停用项' }).getAttribute('aria-disabled')).toBe(
      'true',
    )
    await user.click(screen.getByRole('option', { name: '已启动' }))
    expect(changed).toHaveBeenCalledExactlyOnceWith('started')
    expect(trigger.textContent).toBe('已启动')
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })
  it('方向键跳过禁用项、Enter 选中、Escape 关闭且不改变值', async () => {
    const user = userEvent.setup(),
      changed = vi.fn()
    render(<Field changed={changed} />)
    const trigger = screen.getByRole('combobox', { name: '赛事状态' })
    trigger.focus()
    await user.keyboard('{Enter}{ArrowDown}{Enter}')
    expect(changed).toHaveBeenLastCalledWith('started')
    await user.keyboard('{Enter}{ArrowUp}{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(changed).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })
  it('全部选项仍向调用方传空字符串，不泄漏内部映射值', async () => {
    const user = userEvent.setup(),
      changed = vi.fn()
    render(<Field changed={changed} />)
    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: '全部状态' }))
    expect(changed).toHaveBeenCalledExactlyOnceWith('')
    expect(screen.getByRole('combobox').textContent).toBe('全部状态')
  })
  it('受控更新、禁用及无障碍信息保持一致', async () => {
    const changed = vi.fn(),
      user = userEvent.setup()
    const props = { 'aria-label': '设备状态', options, onValueChange: changed } as const
    const { rerender } = render(<Select {...props} value="draft" />)
    rerender(
      <Select {...props} value="started" disabled required aria-invalid aria-describedby="help" />,
    )
    const trigger = screen.getByRole('combobox', { name: '设备状态' }) as HTMLButtonElement
    expect(trigger.textContent).toBe('已启动')
    expect(trigger.disabled).toBe(true)
    expect(trigger.getAttribute('aria-required')).toBe('true')
    expect(trigger.getAttribute('aria-describedby')).toBe('help')
    expect(trigger.getAttribute('aria-invalid')).toBe('true')
    await user.click(trigger)
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(changed).not.toHaveBeenCalled()
  })
  it('表单序列化使用原值，空值保留 required 校验能力', async () => {
    const { container, rerender } = render(
      <form>
        <Select
          aria-label="规则"
          name="rule"
          required
          value="draft"
          options={options}
          onValueChange={() => {}}
        />
      </form>,
    )
    const form = container.querySelector('form')!
    expect(new FormData(form).get('rule')).toBe('draft')
    rerender(
      <form>
        <Select
          aria-label="规则"
          name="rule"
          required
          value=""
          options={options}
          onValueChange={() => {}}
        />
      </form>,
    )
    expect(new FormData(form).get('rule')).toBe('')
    expect(form.checkValidity()).toBe(false)
    // Radix's visually hidden form bridge is never an interactive native menu.
    expect(container.querySelector('select')?.getAttribute('aria-hidden')).toBe('true')
  })
  it('长文字和大量动态选项仍使用同一菜单与完整可访问名称', async () => {
    const user = userEvent.setup(),
      long = '很长的真实选项名称'.repeat(12)
    render(
      <Select
        aria-label="物理桌"
        value=""
        onValueChange={() => {}}
        options={Array.from({ length: 40 }, (_, i) => ({
          value: i + 1,
          label: `${i + 1} · ${long}`,
        }))}
      />,
    )
    await user.click(screen.getByRole('combobox'))
    expect(screen.getAllByRole('option')).toHaveLength(40)
    expect(screen.getByRole('option', { name: `40 · ${long}` })).toBeTruthy()
    expect(screen.getByRole('listbox').getAttribute('data-slot')).toBe('select-content')
  })
  it('Sheet 内首次 Escape 只关闭下拉，第二次关闭 Sheet', async () => {
    const user = userEvent.setup(),
      close = vi.fn()
    render(
      <Sheet open onOpenChange={close}>
        <SheetContent>
          <SheetTitle>表单</SheetTitle>
          <SheetDescription>测试弹层</SheetDescription>
          <Field />
        </SheetContent>
      </Sheet>,
    )
    await user.click(screen.getByRole('combobox'))
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(screen.getByRole('dialog', { name: '表单' })).toBeTruthy()
    expect(close).not.toHaveBeenCalled()
    await user.keyboard('{Escape}')
    expect(close).toHaveBeenCalledWith(false)
  })
})
