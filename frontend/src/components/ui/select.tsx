import { Select as SelectPrimitive } from 'radix-ui'
import { Check, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'

export type SelectOption = { value: string | number; label: string; disabled?: boolean }
type SelectProps = {
  value: string | number | undefined
  onValueChange: (value: string) => void
  options: readonly SelectOption[]
  'aria-label': string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
  id?: string
  name?: string
  disabled?: boolean
  required?: boolean
  className?: string
}

// Radix Item reserves the empty string for clearing. Translate only inside the
// component; filters, forms and API callers keep their original empty value.
const emptyItem = '__riichi_select_empty__'

export function Select({
  value,
  onValueChange,
  options,
  disabled,
  required,
  name,
  className,
  ...triggerProps
}: SelectProps) {
  return (
    <SelectPrimitive.Root
      value={value === undefined ? '' : String(value)}
      onValueChange={(next) => onValueChange(next === emptyItem ? '' : next)}
      disabled={disabled}
      required={required}
      name={name}
    >
      <SelectPrimitive.Trigger
        data-slot="select-trigger"
        className={cn('riichi-select-trigger', className)}
        {...triggerProps}
      >
        <SelectPrimitive.Value
          placeholder={options.find((option) => option.value === '')?.label || '请选择'}
        />
        <SelectPrimitive.Icon asChild>
          <ChevronDown size={16} aria-hidden="true" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          data-slot="select-content"
          className="riichi-select-content"
          position="popper"
          // Track Sheet transforms as well as scroll/resize while the menu is open.
          updatePositionStrategy="always"
          sideOffset={6}
          collisionPadding={12}
          avoidCollisions
        >
          <SelectPrimitive.ScrollUpButton className="riichi-select-scroll">
            <ChevronUp size={16} aria-hidden="true" />
          </SelectPrimitive.ScrollUpButton>
          <SelectPrimitive.Viewport className="riichi-select-viewport">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value === '' ? emptyItem : String(option.value)}
                disabled={option.disabled}
                className="riichi-select-item"
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className="riichi-select-indicator">
                  <Check size={16} aria-hidden="true" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
          <SelectPrimitive.ScrollDownButton className="riichi-select-scroll">
            <ChevronDown size={16} aria-hidden="true" />
          </SelectPrimitive.ScrollDownButton>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}
