#!/usr/bin/env python3
"""Generate mock prompt + chapter data for INKCOPY (all modes).

Run:  python tests/make_mock_data.py
Creates ./mock-data/{prompts,chapters,output} relative to repo root.

The data is deliberately mixed-language (English + Thai) because INKCOPY's
real workload is Thai web-novel translation and several code paths depend on
correct Unicode/UTF-8 handling (BOM detection, NFC normalization, etc.).
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK = os.path.join(ROOT, "mock-data")

PROMPTS = {
    "system-prompt.txt": (
        "You are a professional Thai-to-English web-novel translator.\n"
        "Translate the chapter below into natural English.\n"
        "Keep character names consistent. Preserve paragraph breaks.\n"
    ),
    "glossary.txt": (
        "Glossary (keep these translations consistent):\n"
        "อาคม = Arkom (protagonist)\n"
        "นพเก้า = Noppakao (city)\n"
        "ดาบเทพ = Divine Blade\n"
    ),
}

# Six numbered chapters so natsort + trailing-digit chapter detection have
# something real to chew on (chapter0001 .. chapter0006).
CHAPTERS = {
    f"chapter{n:04d}.txt": (
        f"บทที่ {n}\n\n"
        f"อาคมเดินเข้าไปในเมืองนพเก้าเป็นครั้งแรก ตอนที่ {n}.\n"
        f"He gripped the Divine Blade and stepped through the gate. (chapter {n})\n"
    )
    for n in range(1, 7)
}


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # utf-8-sig so downstream apps detect UTF-8, matching how INKCOPY writes.
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(text)


def main() -> None:
    for name, text in PROMPTS.items():
        _write(os.path.join(MOCK, "prompts", name), text)
    for name, text in CHAPTERS.items():
        _write(os.path.join(MOCK, "chapters", name), text)
    # Copy-mode output target (kept empty; tests write here).
    os.makedirs(os.path.join(MOCK, "output"), exist_ok=True)
    open(os.path.join(MOCK, "output", ".gitkeep"), "w").close()
    print(f"Mock data written under {MOCK}")
    print(f"  prompts:  {len(PROMPTS)}  ({', '.join(PROMPTS)})")
    print(f"  chapters: {len(CHAPTERS)} ({', '.join(CHAPTERS)})")


if __name__ == "__main__":
    main()
