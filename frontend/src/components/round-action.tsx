import { X } from 'lucide-react'
import { Button } from './ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet'
import type { RoundTable } from '@/services/rounds'

/** Read-only F0-05 audit. New resource writes use the tournament workflow. */
export function RoundActionSheet({ table, close }: { table: RoundTable; close: () => void }) {
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) close()
      }}
    >
      <SheetContent className="machine-sheet tournament-sheet" showCloseButton={false}>
        <SheetHeader>
          <span className="eyebrow">LEGACY ALLOCATION AUDIT</span>
          <SheetTitle>旧版轮次分配历史</SheetTitle>
          <SheetDescription>
            第 {table.round_number} 轮 · 逻辑桌 {'ABCD'[table.table_number - 1]} · 原记录只读
          </SheetDescription>
        </SheetHeader>
        <Button
          className="machine-sheet-close"
          size="icon"
          variant="ghost"
          aria-label="关闭旧版分配历史"
          onClick={close}
        >
          <X />
        </Button>
        <div className="competition-action-body allocation-history">
          {table.allocation_history.map((a) => (
            <article key={a.id}>
              <strong>物理桌 {a.machine_no_snapshot}</strong>
              <p>
                稳定 machineId #{a.machine_id} · 原分配 ID #{a.id}
              </p>
              <p>
                当前编号 {a.machine_no} · {a.status === 'active' ? '原占用仍有效' : '已释放'}
              </p>
              <p>
                分配：{new Date(a.allocated_at).toLocaleString('zh-CN')} · 管理员 #{a.allocated_by}
              </p>
              {a.released_at && (
                <p>
                  释放：{new Date(a.released_at).toLocaleString('zh-CN')} · 管理员 #{a.released_by}{' '}
                  · {a.release_reason || '未填写说明'}
                </p>
              )}
            </article>
          ))}
          <Button variant="outline" onClick={close}>
            关闭
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
