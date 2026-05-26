// Chapter filename utilities — ported from inkcopy.py
//   _clean_chapter_stem / _split_stem_trailing_digits / _detect_chapter_number
//   copy_mode_group_output_name
// Keep behavior parity 1:1 so chapter sort order matches the Python build
// when the same folder is opened in both versions.

const TRAILING_PUNCT = ' \t._-—：:=＆&）)】]'

/** NFC + trim + strip BOM so noisy filename variants compare cleanly. */
export function cleanChapterStem(stem: string): string {
  return stem.normalize('NFC').trim().replace(/^﻿/, '')
}

/** Compare prefix ignoring outer space, internal whitespace runs, ASCII case. */
export function canonicalPrefixKey(prefix: string): string {
  return prefix.normalize('NFC').trim().replace(/\s+/g, ' ').toLowerCase()
}

function isAsciiDigitRun(s: string): boolean {
  return s.length > 0 && /^[0-9]+$/.test(s)
}

/**
 * Split stem into [prefix, trailingDigits] tuple, or null when no trailing
 * ASCII digits exist. Tries the cleaned stem then a rstrip of common trailing
 * punctuation so "Episode_007." matches.
 */
export function splitStemTrailingDigits(stem: string): [string, string] | null {
  const cleaned = cleanChapterStem(stem)
  if (!cleaned) return null

  const candidates: string[] = [cleaned]
  let stripped = cleaned
  while (stripped.length && TRAILING_PUNCT.includes(stripped[stripped.length - 1])) {
    stripped = stripped.slice(0, -1)
  }
  if (stripped !== cleaned) candidates.push(stripped)

  const seen = new Set<string>()
  for (const cand of candidates) {
    if (!cand || seen.has(cand)) continue
    seen.add(cand)
    const m = cand.match(/(\d+)$/)
    if (!m) continue
    const digits = m[1]
    if (!isAsciiDigitRun(digits)) continue
    const prefix = cand.slice(0, cand.length - digits.length)
    return [prefix, digits]
  }
  return null
}

/** Filename → trailing chapter number (e.g. "Chapter 11.txt" → 11). */
export function detectChapterNumber(filename: string): number | null {
  const stem = filename.replace(/\.[^.]+$/, '')
  const split = splitStemTrailingDigits(stem)
  if (!split) return null
  const n = parseInt(split[1], 10)
  return Number.isFinite(n) ? n : null
}

/**
 * Output filename + title stem for a Copy-mode save spanning a chapter range.
 * Falls back to the first chapter's filename when no safe range can form.
 */
export function copyModeGroupOutputName(firstName: string, lastName: string): { fileName: string; stem: string } {
  const firstStem = firstName.replace(/\.[^.]+$/, '')
  const lastStem = lastName.replace(/\.[^.]+$/, '')
  const ext = firstName.match(/\.[^.]+$/)?.[0] ?? ''

  if (cleanChapterStem(firstStem) === cleanChapterStem(lastStem)) {
    return { fileName: firstName, stem: firstStem }
  }
  const a0 = splitStemTrailingDigits(firstStem)
  const a1 = splitStemTrailingDigits(lastStem)
  if (!a0 || !a1) return { fileName: firstName, stem: firstStem }
  if (canonicalPrefixKey(a0[0]) !== canonicalPrefixKey(a1[0])) {
    return { fileName: firstName, stem: firstStem }
  }
  const n0 = parseInt(a0[1], 10)
  const n1 = parseInt(a1[1], 10)
  if (!Number.isFinite(n0) || !Number.isFinite(n1)) {
    return { fileName: firstName, stem: firstStem }
  }
  const width = Math.max(a0[1].length, a1[1].length)
  const left = String(n0).padStart(width, '0')
  const right = String(n1).padStart(width, '0')
  const stemOut = `${a0[0]}${left}-${right}`
  return { fileName: `${stemOut}${ext}`, stem: stemOut }
}

/**
 * Natural-sort comparator matching Python `natsort.natsorted`. Splits each
 * string into runs of digits vs non-digits and compares run-by-run with
 * numeric vs case-insensitive lexical ordering.
 */
export function naturalCompare(a: string, b: string): number {
  const ax: Array<string | number> = []
  const bx: Array<string | number> = []
  for (const m of a.matchAll(/(\d+)|(\D+)/g)) {
    ax.push(m[1] !== undefined ? Number(m[1]) : m[2]!.toLowerCase())
  }
  for (const m of b.matchAll(/(\d+)|(\D+)/g)) {
    bx.push(m[1] !== undefined ? Number(m[1]) : m[2]!.toLowerCase())
  }
  for (let i = 0; i < Math.min(ax.length, bx.length); i++) {
    const av = ax[i]
    const bv = bx[i]
    if (typeof av === 'number' && typeof bv === 'number') {
      if (av !== bv) return av - bv
    } else {
      const aStr = String(av)
      const bStr = String(bv)
      if (aStr !== bStr) return aStr < bStr ? -1 : 1
    }
  }
  return ax.length - bx.length
}
