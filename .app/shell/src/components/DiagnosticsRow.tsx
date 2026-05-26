import { useEffect } from 'react'
import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'

/**
 * Diagnostics row — port of SmartClipboardOverlay._diagnostics_tick() in
 * inkcopy.py. Polls hotkey stats + permission state every 2s; surfaces the
 * "no keys observed" hint when the listener is alive but receiving nothing.
 */
export function DiagnosticsRow() {
  const hotkeysRegistered = useStore((s) => s.hotkeysRegistered)
  const stats = useStore((s) => s.hotkeyStats)
  const permissions = useStore((s) => s.permissions)
  const setHotkeyStats = useStore((s) => s.setHotkeyStats)
  const setPermissions = useStore((s) => s.setPermissions)

  useEffect(() => {
    let cancelled = false

    const refresh = async () => {
      try {
        const next = await window.inkcopy?.hotkey?.stats()
        if (!cancelled && next) setHotkeyStats(next)
      } catch {
        /* mock IPC during dev — ignore */
      }
      try {
        const perm = await window.inkcopy?.permissions?.check()
        if (!cancelled && perm) setPermissions(perm)
      } catch {
        /* mock IPC during dev — ignore */
      }
    }
    refresh()
    const id = window.setInterval(refresh, 2000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [setHotkeyStats, setPermissions])

  const bits: Array<{ tone: 'ok' | 'warn' | 'err' | 'muted'; text: string; icon: string }> = []
  const isMac = !!window.inkcopy?.isMac

  if (isMac && permissions.runningFromDmg) {
    bits.push({
      tone: 'err',
      icon: 'warning',
      text: 'รันจาก DMG — ลาก INKCOPY.app ไป /Applications/ ก่อน permission ถึงจะติด',
    })
  }
  if (isMac) {
    if (permissions.accessibilityTrusted === false) {
      bits.push({ tone: 'err', icon: 'error', text: 'Accessibility: ยังไม่ trust — System Settings → Privacy & Security' })
    } else if (permissions.accessibilityTrusted === true) {
      bits.push({ tone: 'ok', icon: 'check', text: 'Accessibility: trusted' })
    }
    if (permissions.inputMonitoringTrusted === false) {
      bits.push({ tone: 'err', icon: 'error', text: 'Input Monitoring: ยังไม่ granted — เปิดใน System Settings ก่อน' })
    } else if (permissions.inputMonitoringTrusted === true) {
      bits.push({ tone: 'ok', icon: 'check', text: 'Input Monitoring: granted' })
    }
  }

  if (!hotkeysRegistered) {
    bits.push({ tone: 'muted', icon: 'circle-outline', text: 'ยังไม่พร้อมใช้ — เลือกโฟลเดอร์ Prompt + ตอนก่อน แล้วกดปุ่ม "เริ่มใช้งาน"' })
  } else {
    bits.push({
      tone: 'ok',
      icon: 'pulse',
      text: `ทำงานอยู่ · keys=${stats.keysReceived} V=${stats.vKeysSeen} วาง=${stats.pasteFires} F9=${stats.prevFires} F10=${stats.nextFires}`,
    })
    if (isMac && hotkeysRegistered && stats.keysReceived === 0) {
      bits.push({ tone: 'warn', icon: 'warning', text: 'ยังไม่เห็นปุ่มที่กดเลย — ตรวจสอบ Input Monitoring แล้ว Quit & เปิดใหม่' })
    }
  }

  if (stats.lastError) {
    bits.push({ tone: 'err', icon: 'error', text: `ข้อผิดพลาดล่าสุด: ${stats.lastError}` })
  }

  return (
    <div className="flex items-start gap-2 rounded-sm border border-vscode-border bg-vscode-input/40 px-2.5 py-1.5">
      <div className="flex flex-1 flex-wrap gap-x-3 gap-y-1 text-[13px]">
        {bits.map((b, i) => (
          <span
            key={i}
            data-testid={`diag-bit-${b.tone}`}
            className={
              b.tone === 'ok'
                ? 'flex items-center gap-1 text-vscode-success'
                : b.tone === 'warn'
                  ? 'flex items-center gap-1 text-yellow-300'
                  : b.tone === 'err'
                    ? 'flex items-center gap-1 text-red-400'
                    : 'flex items-center gap-1 text-vscode-muted'
            }
          >
            <Codicon name={b.icon} size={11} />
            <span>{b.text}</span>
          </span>
        ))}
      </div>
      <button
        type="button"
        onClick={async () => {
          const p = await window.inkcopy?.log?.getLogPath()
          if (p) await window.inkcopy?.shell?.showItemInFolder(p)
        }}
        className="flex h-7 shrink-0 items-center gap-1 rounded-sm border border-vscode-border bg-vscode-button px-2 text-[13px] text-vscode-fg hover:bg-vscode-list-hover"
        title="เปิดโฟลเดอร์ log file"
        data-testid="open-log"
      >
        <Codicon name="search" size={11} />
        <span>Open Log</span>
      </button>
    </div>
  )
}
