import { useState, type FormEvent } from 'react'
import { X, Archive } from 'lucide-react'
import { Button } from './ui/button'
import { Select } from './ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import { FormFeedback } from './form-feedback'
import {
  machineLabels,
  saveMachine,
  retireMachine,
  type Machine,
  type MachineInput,
} from '@/services/machines'

export function MachineEditor({
  machine,
  readOnly = false,
  close,
  saved,
}: {
  machine?: Machine
  readOnly?: boolean
  close: () => void
  saved: (machine: Machine) => void
}) {
  const [values, setValues] = useState<MachineInput>({
    machine_no: machine?.machine_no || '',
    name: machine?.name || '',
    location: machine?.location || '',
    description: machine?.description || '',
    status: machine?.status === 'retired' ? 'available' : machine?.status || 'available',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  function field<K extends keyof MachineInput>(key: K, value: MachineInput[K]) {
    setValues((previous) => ({ ...previous, [key]: value }))
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (!/^[0-9]{1,3}$/.test(values.machine_no.trim())) {
      setError(new Error('设备编号必须为 1～3 位数字。'))
      return
    }
    if (!values.name.trim()) {
      setError(new Error('设备名称不能为空。'))
      return
    }
    setBusy(true)
    try {
      saved(
        await saveMachine(
          {
            ...values,
            machine_no: values.machine_no.trim(),
            name: values.name.trim(),
            location: values.location.trim(),
            description: values.description.trim(),
          },
          machine?.id,
        ),
      )
    } catch (problem) {
      setError(problem instanceof Error ? problem : new Error('保存失败，请检查设备列表后重试。'))
    } finally {
      setBusy(false)
    }
  }
  const title = readOnly ? '设备详情' : machine ? '编辑设备' : '新建设备'
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy) close()
      }}
    >
      <SheetContent className="machine-sheet" showCloseButton={false}>
        <SheetHeader>
          <span className="eyebrow">MACHINE RESOURCE</span>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            {machine
              ? `设备编号 ${machine.machine_no} · 稳定 ID #${machine.id}`
              : '为物理麻将机建立独立档案，设备编号保存为三位数字。'}
          </SheetDescription>
        </SheetHeader>
        <Button
          variant="ghost"
          size="icon"
          className="machine-sheet-close"
          disabled={busy}
          onClick={close}
          aria-label="关闭设备表单"
        >
          <X />
        </Button>
        <form className="account-form machine-form" onSubmit={submit}>
          <fieldset disabled={busy || readOnly}>
            <label>
              设备编号
              <input
                autoFocus={!readOnly}
                name="machine_no"
                value={values.machine_no}
                onChange={(e) => field('machine_no', e.target.value)}
                inputMode="numeric"
                maxLength={3}
                required
                placeholder="例如 007"
              />
            </label>
            <p className="field-hint">编号不限于 001～004，现役设备之间不得重复。</p>
            <label>
              设备名称
              <input
                name="name"
                value={values.name}
                onChange={(e) => field('name', e.target.value)}
                maxLength={100}
                required
              />
            </label>
            <label>
              设备位置<span className="field-optional">可选</span>
              <input
                name="location"
                value={values.location}
                onChange={(e) => field('location', e.target.value)}
                maxLength={200}
              />
            </label>
            {machine?.status === 'retired' ? (
              <p className="retired-notice">已退役 · 历史资料只读，不能重新启用。</p>
            ) : (
              <label>
                设备状态
                <Select
                  aria-label="设备状态"
                  name="status"
                  value={values.status}
                  disabled={busy || readOnly}
                  onValueChange={(value) => field('status', value as MachineInput['status'])}
                  options={(['available', 'maintenance', 'disabled'] as const).map((status) => ({
                    value: status,
                    label: machineLabels[status],
                  }))}
                />
              </label>
            )}
            <label>
              备注<span className="field-optional">可选</span>
              <textarea
                name="description"
                value={values.description}
                onChange={(e) => field('description', e.target.value)}
                maxLength={2000}
                rows={4}
              />
            </label>
          </fieldset>
          {readOnly && machine && (
            <dl className="machine-dates">
              <div>
                <dt>创建时间</dt>
                <dd>{new Date(machine.created_at).toLocaleString('zh-CN')}</dd>
              </div>
              <div>
                <dt>更新时间</dt>
                <dd>{new Date(machine.updated_at).toLocaleString('zh-CN')}</dd>
              </div>
            </dl>
          )}
          <FormFeedback error={error} />
          <div className="machine-form-footer">
            <Button variant="outline" type="button" disabled={busy} onClick={close}>
              {readOnly ? '关闭' : '取消'}
            </Button>
            {!readOnly && (
              <Button type="submit" disabled={busy}>
                {busy ? '正在保存…' : machine ? '保存修改' : '创建设备'}
              </Button>
            )}
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}

export function MachineRetirement({
  machine,
  close,
  saved,
}: {
  machine: Machine
  close: () => void
  saved: (machine: Machine) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      saved(await retireMachine(machine.id))
    } catch (problem) {
      setError(problem as Error)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !busy) close()
      }}
    >
      <SheetContent className="machine-sheet retire-sheet" showCloseButton={false}>
        <SheetHeader>
          <Archive className="retire-icon" />
          <SheetTitle>确认退役设备</SheetTitle>
          <SheetDescription>退役后将释放现役容量，历史档案和稳定 ID 将保留。</SheetDescription>
        </SheetHeader>
        <div className="retirement-body">
          <span className="machine-number">{machine.machine_no}</span>
          <h3>{machine.name}</h3>
          <p>{machine.location || '未填写位置'}</p>
          <div className="retirement-warning">
            此操作不可直接撤销。设备退役后不能编辑或重新启用，请确认对应的物理设备已退出资源池。
          </div>
          <FormFeedback error={error} />
          <div className="machine-form-footer">
            <Button variant="outline" disabled={busy} onClick={close}>
              取消退役
            </Button>
            <Button variant="destructive" disabled={busy} onClick={() => void confirm()}>
              {busy ? '正在退役…' : '确认退役'}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
