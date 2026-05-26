import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useStore } from '../state/store'
import type { ToastEntry } from '../types/inkcopy'
import { Codicon } from '../ui/Codicon'
import { cn } from '../ui/cn'

const TONE_STYLE: Record<ToastEntry['tone'], string> = {
  paste: 'bg-vscode-brand/90 text-vscode-titlebar border-vscode-brand',
  copy: 'bg-emerald-500/90 text-white border-emerald-400',
  vocab: 'bg-violet-500/90 text-white border-violet-400',
  info: 'bg-vscode-button text-vscode-fg border-vscode-border',
  error: 'bg-red-500/90 text-white border-red-400',
}

const TONE_ICON: Record<ToastEntry['tone'], string> = {
  paste: 'clippy',
  copy: 'copy',
  vocab: 'book',
  info: 'info',
  error: 'error',
}

function ToastCard({ toast, onClose }: { toast: ToastEntry; onClose: () => void }) {
  useEffect(() => {
    if (toast.durationMs <= 0) return
    const id = window.setTimeout(onClose, toast.durationMs)
    return () => window.clearTimeout(id)
  }, [toast.id, toast.durationMs, onClose])

  return (
    <div
      className={cn(
        'pointer-events-auto flex items-center gap-2 rounded-sm border px-3 py-2 text-[13px] shadow-lg',
        TONE_STYLE[toast.tone],
      )}
      data-testid="toast"
      data-tone={toast.tone}
    >
      <Codicon name={TONE_ICON[toast.tone]} size={14} />
      <span className="flex-1">{toast.message}</span>
      <button
        type="button"
        onClick={onClose}
        className="opacity-70 hover:opacity-100"
        aria-label="ปิด"
      >
        <Codicon name="close" size={11} />
      </button>
    </div>
  )
}

export function ToastStack() {
  const toasts = useStore((s) => s.toasts)
  const dismissToast = useStore((s) => s.dismissToast)
  if (typeof document === 'undefined') return null

  return createPortal(
    <div
      className="pointer-events-none fixed bottom-4 left-1/2 z-[1000] flex w-[min(94vw,420px)] -translate-x-1/2 flex-col gap-1.5"
      role="region"
      aria-label="การแจ้งเตือน"
    >
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} onClose={() => dismissToast(t.id)} />
      ))}
    </div>,
    document.body,
  )
}
