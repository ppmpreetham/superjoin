"""PDF ingestion: page text extraction + chunking with page-aware metadata."""
from dataclasses import dataclass, field

import pymupdf

from .config import CHUNK_CHARS, CHUNK_OVERLAP


@dataclass
class Chunk:
    doc_id: str
    doc_name: str
    page: int  # 1-based PDF page
    text: str


@dataclass
class ParsedDoc:
    doc_id: str
    doc_name: str
    num_pages: int
    pages: dict[int, str]  # page number -> text
    chunks: list[Chunk] = field(default_factory=list)


def parse_pdf(path, doc_id: str, doc_name: str) -> ParsedDoc:
    """Extract per-page text from a PDF and build overlapping fixed-size chunks."""
    doc = pymupdf.open(path)
    pages: dict[int, str] = {}
    for i, page in enumerate(doc):
        pages[i + 1] = page.get_text("text").strip()
    num_pages = len(doc)
    doc.close()

    chunks: list[Chunk] = []
    # Chunk per page when pages are small; merge sparse pages, split dense ones.
    buf_page, buf_text = None, ""
    for page in sorted(pages):
        text = pages[page]
        if not text:
            continue
        if len(text) > CHUNK_CHARS:
            # Flush buffer, then split the dense page with overlap.
            if buf_text:
                chunks.append(Chunk(doc_id, doc_name, buf_page, buf_text))
                buf_page, buf_text = None, ""
            start = 0
            while start < len(text):
                chunks.append(
                    Chunk(doc_id, doc_name, page, text[start : start + CHUNK_CHARS])
                )
                start += CHUNK_CHARS - CHUNK_OVERLAP
            continue
        if buf_text and len(buf_text) + len(text) + 1 <= CHUNK_CHARS:
            buf_text += "\n" + text
        else:
            if buf_text:
                chunks.append(Chunk(doc_id, doc_name, buf_page, buf_text))
            buf_page, buf_text = page, text
    if buf_text:
        chunks.append(Chunk(doc_id, doc_name, buf_page, buf_text))

    return ParsedDoc(doc_id, doc_name, num_pages, pages, chunks)
