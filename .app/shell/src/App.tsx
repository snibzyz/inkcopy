import { AppButton, AppCard, Codicon, Input, MacFieldLabel, MacPanel } from './ui'

export default function App() {
  return (
    <div className="flex h-screen flex-col bg-vscode-editor text-vscode-fg">
      <header className="flex h-9 items-center border-b border-vscode-border bg-vscode-titlebar px-3 text-[12px]">
        <Codicon name="symbol-method" className="text-vscode-brand" />
        <span className="ml-2 font-semibold text-vscode-fg-bright">INKCOPY</span>
      </header>

      <main className="flex flex-1 gap-3 overflow-hidden p-3">
        <aside className="w-[200px] shrink-0">
          <MacPanel className="h-full">
            <div className="text-[11px] uppercase tracking-[0.08em] text-vscode-muted">Sidebar</div>
          </MacPanel>
        </aside>

        <section className="flex-1 overflow-auto">
          <AppCard title="ยินดีต้อนรับ" description="แอปใหม่จาก .shared starter">
            <div className="space-y-3">
              <div>
                <MacFieldLabel>ชื่อ</MacFieldLabel>
                <Input placeholder="กรอกชื่อ..." />
              </div>
              <div className="flex gap-2">
                <AppButton tone="primary">บันทึก</AppButton>
                <AppButton tone="zinc" variant="flat">ยกเลิก</AppButton>
              </div>
            </div>
          </AppCard>
        </section>
      </main>

      <footer className="flex h-6 items-center border-t border-vscode-border bg-vscode-statusbar px-3 text-[11px] text-white">
        พร้อมใช้งาน
      </footer>
    </div>
  )
}
