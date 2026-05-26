/**
 * Codicon — React wrapper รอบ @vscode/codicons icon font
 *
 * ต้อง import css ของ @vscode/codicons ไว้ใน entry (เช่น main.tsx):
 *   import '@vscode/codicons/dist/codicon.css'
 *
 * ใช้: <Codicon name="gear" />, <Codicon name="folder-opened" size={14} />
 * รายชื่อ glyph: https://microsoft.github.io/vscode-codicons/dist/codicon.html
 */

import { cn } from './cn'
import type { CSSProperties, HTMLAttributes } from 'react'

export type CodiconName = string

export type CodiconProps = Omit<HTMLAttributes<HTMLSpanElement>, 'children'> & {
  name: CodiconName
  /** font-size px ของ glyph (default 14 — พอดีกับ text-[12px]) */
  size?: number
  /** เปิด animation spin (สำหรับ loading) */
  spin?: boolean
}

export function Codicon({ name, size = 14, spin = false, className, style, ...rest }: CodiconProps) {
  const finalStyle: CSSProperties = {
    ...style,
    fontSize: size,
    lineHeight: `${size}px`,
    width: size,
    height: size,
  }
  return (
    <span
      role="img"
      aria-hidden
      className={cn(
        'codicon inline-flex shrink-0 items-center justify-center align-[-2px]',
        `codicon-${name}`,
        spin ? 'codicon-modifier-spin' : '',
        className
      )}
      style={finalStyle}
      {...rest}
    />
  )
}
