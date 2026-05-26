import { useStore } from '../state/store'
import { Codicon } from '../ui/Codicon'

function chapterLabel(name: string | undefined): string {
  if (!name) return '—'
  return name.replace(/\.[^.]+$/, '')
}

/**
 * Status row — mirrors SmartClipboardOverlay._update_status() in inkcopy.py.
 * Resolves the message from the current mode + folder state without taking
 * any action; it's a pure derived view.
 */
export function StatusBar() {
  const mode = useStore((s) => s.mode)
  const paused = useStore((s) => s.paused)
  const promptFiles = useStore((s) => s.promptFiles)
  const chapterFiles = useStore((s) => s.chapterFiles)
  const currentIndex = useStore((s) => s.currentIndex)
  const concurrent = useStore((s) => s.concurrentChapters)
  const vocabEntryCount = useStore((s) => s.vocabEntryCount)

  let label = '— เลือกโฟลเดอร์ก่อน —'
  let icon = 'info'
  let tone: 'muted' | 'success' | 'warn' | 'brand' = 'muted'

  if (paused) {
    label = '⏸ หยุดชั่วคราว — กด F12 เพื่อใช้ต่อ'
    icon = 'debug-pause'
    tone = 'warn'
  } else if (mode === 'paste') {
    if (!promptFiles.length || !chapterFiles.length) {
      label = '— เลือกโฟลเดอร์ Prompt + ตอนก่อน —'
    } else if (currentIndex >= chapterFiles.length) {
      label = 'เสร็จแล้ว · วางครบทุกตอน'
      icon = 'check'
      tone = 'success'
    } else {
      const total = chapterFiles.length
      const remaining = total - currentIndex
      const toPaste = Math.min(concurrent, remaining)
      const pc = promptFiles.length
      if (toPaste === 1) {
        const ch = chapterFiles[currentIndex]?.displayName
        label = `พร้อมวาง · ${pc} Prompt + ${chapterLabel(ch)} (${currentIndex + 1}/${total})`
      } else {
        const end = currentIndex + toPaste - 1
        const rounds = Math.ceil(remaining / concurrent)
        const first = chapterLabel(chapterFiles[currentIndex]?.displayName)
        const last = chapterLabel(chapterFiles[end]?.displayName)
        label = `พร้อมวาง · ${pc} Prompt + ${first}…${last} (${currentIndex + 1}-${end + 1}/${total}, เหลือ ${rounds} รอบ)`
      }
      icon = 'clippy'
      tone = 'brand'
    }
  } else if (mode === 'copy') {
    if (!chapterFiles.length) {
      label = '— เลือกโฟลเดอร์ตอน + โฟลเดอร์ปลายทางก่อน —'
    } else if (currentIndex >= chapterFiles.length) {
      label = 'เสร็จแล้ว · บันทึกครบทุกตอน'
      icon = 'check'
      tone = 'success'
    } else {
      const ch = chapterLabel(chapterFiles[currentIndex]?.displayName)
      label = `รอ Copy ข้อความสำหรับ · ${ch} (${currentIndex + 1}/${chapterFiles.length})`
      icon = 'copy'
      tone = 'brand'
    }
  } else {
    label = `โหมดศัพท์ · พร้อมเพิ่ม entry (ปัจจุบัน ${vocabEntryCount} entry)`
    icon = 'book'
    tone = 'brand'
  }

  const toneClass =
    tone === 'success'
      ? 'text-vscode-success'
      : tone === 'warn'
        ? 'text-yellow-300'
        : tone === 'brand'
          ? 'text-vscode-brand'
          : 'text-vscode-muted'

  return (
    <div className={`flex items-center gap-2 rounded-sm bg-vscode-input/40 px-3 py-2 text-[13px] ${toneClass}`} data-testid="status-bar">
      <Codicon name={icon} size={14} />
      <span className="truncate">{label}</span>
    </div>
  )
}
