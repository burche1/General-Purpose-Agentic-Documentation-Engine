"""Local, read-only parsers for common document formats.

Returns source-located text blocks. Untrusted document text is data, never instructions.
No OCR, network access, or command execution is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import csv
import re

SUPPORTED = {'.md', '.markdown', '.txt', '.rst', '.pdf', '.docx', '.html', '.htm', '.csv', '.xlsx', '.pptx'}
MAX_FILE_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class Block:
    text: str
    locator: str
    kind: str = 'text'


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.nodes: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in {'script', 'style', 'noscript'}:
            self.depth += 1
        if tag in {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'section'}:
            self._flush()

    def handle_endtag(self, tag: str):
        if tag in {'script', 'style', 'noscript'} and self.depth:
            self.depth -= 1
        if tag in {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'section'}:
            self._flush()

    def handle_data(self, data: str):
        if not self.depth and data.strip():
            self._parts.append(data)

    def _flush(self):
        text = ' '.join(' '.join(self._parts).split())
        if text:
            self.nodes.append(text)
        self._parts.clear()

    def close(self):
        self._flush()
        super().close()


def _text_blocks(path: Path) -> list[Block]:
    # Replacement decoding is deliberate; prevent single bad bytes from hiding a whole document.
    content = path.read_text(encoding='utf-8-sig', errors='replace')
    lines = content.splitlines()
    blocks: list[Block] = []
    buf: list[str] = []
    start_line = 1
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            if buf:
                blocks.append(Block('\n'.join(buf), f'lines {start_line}-{i - 1}'))
                buf = []
        else:
            if not buf:
                start_line = i
            buf.append(line)
    if buf:
        blocks.append(Block('\n'.join(buf), f'lines {start_line}-{len(lines)}'))
    return blocks


def _pdf_blocks(path: Path) -> list[Block]:
    import pymupdf
    out = []
    with pymupdf.open(str(path)) as document:
        if len(document) > 2000:
            raise ValueError('PDF exceeds 2,000 pages; split the document first')
        for page_number, page in enumerate(document, 1):
            content = page.get_text('text', sort=True).strip()
            if content:
                out.append(Block(content, f'page {page_number}', 'pdf_page'))
    return out


def _docx_blocks(path: Path) -> list[Block]:
    from docx import Document
    from docx.table import Table
    doc = Document(path)
    out = []
    for i, item in enumerate(doc.iter_inner_content(), 1):
        if isinstance(item, Table):
            for row_idx, row in enumerate(item.rows, 1):
                parts = [cell.text.strip() for cell in row.cells]
                content = ' | '.join(parts).strip(' |')
                if content:
                    out.append(Block(content, f'table element {i}, row {row_idx}', 'table_row'))
        else:
            content = item.text.strip()
            if content:
                out.append(Block(content, f'paragraph element {i}', 'paragraph'))
    # DOCX headers, footers, comments and drawings are not extracted in this MVP.
    return out


def _csv_blocks(path: Path) -> list[Block]:
    with path.open('r', encoding='utf-8-sig', errors='replace', newline='') as f:
        reader = csv.reader(f)
        header = next(reader, [])
        out = []
        for row_number, row in enumerate(reader, start=2):
            if row_number > 20001:
                raise ValueError('CSV exceeds 20,000 rows; split the file first')
            content = ' | '.join(f'{header[i] if i < len(header) else f"column {i+1}"}: {value}' for i, value in enumerate(row) if value.strip())
            if content:
                out.append(Block(content, f'row {row_number}', 'table_row'))
        return out


def _xlsx_blocks(path: Path) -> list[Block]:
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    blocks = []
    try:
        if len(book.sheetnames) > 40:
            raise ValueError('Workbook exceeds 40 sheets')
        for sheet in book:
            for i, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if i > 20000:
                    raise ValueError(f'Worksheet {sheet.title} exceeds 20,000 rows')
                if len(row) > 150:
                    raise ValueError(f'Worksheet {sheet.title} exceeds 150 columns')
                content = ' | '.join(f'{j + 1}: {cell}' for j, cell in enumerate(row) if cell is not None and str(cell).strip())
                if content:
                    blocks.append(Block(content, f'sheet {sheet.title}, row {i}', 'table_row'))
    finally:
        book.close()
    return blocks


def _pptx_blocks(path: Path) -> list[Block]:
    from pptx import Presentation
    prs = Presentation(path)
    out = []
    if len(prs.slides) > 1000:
        raise ValueError('Presentation exceeds 1,000 slides')
    for i, slide in enumerate(prs.slides, start=1):
        for j, shape in enumerate(slide.shapes, start=1):
            if shape.has_text_frame and shape.text.strip():
                out.append(Block(shape.text.strip(), f'slide {i}, shape {j}', 'slide_text'))
            if shape.has_table:
                for k, row in enumerate(shape.table.rows, 1):
                    content = ' | '.join(cell.text.strip() for cell in row.cells).strip(' |')
                    if content:
                        out.append(Block(content, f'slide {i}, table {j}, row {k}', 'table_row'))
    return out


def extract_document(path: Path) -> list[Block]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f'File exceeds size limit ({MAX_FILE_BYTES // (1024*1024)} MiB)')
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f'Unsupported file extension: {suffix}')
    if suffix in {'.md', '.markdown', '.txt', '.rst'}:
        return _text_blocks(path)
    if suffix == '.pdf':
        return _pdf_blocks(path)
    if suffix == '.docx':
        return _docx_blocks(path)
    if suffix == '.csv':
        return _csv_blocks(path)
    if suffix == '.xlsx':
        return _xlsx_blocks(path)
    if suffix == '.pptx':
        return _pptx_blocks(path)
    parser = _HTMLText()
    parser.feed(path.read_text(encoding='utf-8-sig', errors='replace'))
    parser.close()
    return [Block(text, f'HTML text block {i}') for i, text in enumerate(parser.nodes, start=1)]


def split_blocks(blocks: list[Block], max_chars: int = 1200) -> list[Block]:
    """Split large source blocks into small searchable units; keep the source locator."""
    output = []
    for block in blocks:
        content = block.text.strip()
        if not content:
            continue
        # Keep whole blocks whenever possible. Break oversized blocks on whitespace.
        if len(content) <= max_chars:
            output.append(block)
            continue
        # Tokens longer than the limit are split too: do not leave enormous chunks.
        tokens = re.findall(r'\S+\s*', content)
        buf = ''
        part = 1
        for token in tokens:
            while token:
                room = max_chars - len(buf)
                if room == 0:
                    output.append(Block(buf.strip(), f'{block.locator} (part {part})', block.kind))
                    part += 1
                    buf = ''
                    room = max_chars
                take = token[:room]
                buf += take
                token = token[room:]
        if buf.strip():
            output.append(Block(buf.strip(), f'{block.locator} (part {part})', block.kind))
    return output
