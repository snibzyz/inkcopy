# Sample data for E2E tests

`prompts/` — 2 prompt files (system prompt + glossary)
`chapters/` — 4 chapter files named `chapter0001.txt`–`chapter0004.txt`

These fixtures let `smoke.spec.ts` seed realistic folder paths without
spawning the OS folder picker. The chapter filenames are designed to
exercise `detectChapterNumber` (trailing 4-digit run) and `naturalCompare`
(zero-padded vs unpadded sort).
