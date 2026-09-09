"""Dump page-structured text from the starter PDFs so they can be read as plain text."""
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "starter-datasets" / "starter-datasets"
OUT = ROOT / "backend" / "seed" / "pdf_text"
OUT.mkdir(parents=True, exist_ok=True)

for pdf in sorted(DATASETS.rglob("*.pdf")):
    out_path = OUT / (pdf.stem + ".txt")
    if out_path.exists():
        print(f"skip {out_path.name}")
        continue
    doc = pymupdf.open(pdf)
    parts = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        parts.append(f"\n===== [pdf-page {i+1}] =====\n{text}")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"{pdf.name}: {len(doc)} pages -> {out_path.name} ({sum(len(p) for p in parts)} chars)")
    doc.close()

print("done")
