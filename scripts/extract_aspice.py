#!/usr/bin/env python3
"""Extract selected Automotive SPICE PAM 4.1 processes into one Markdown file.

Uses the original PDF's purpose, outcomes, Base Practice descriptions, and
outcome-mapping tables (the X-marked columns), including multi-page tables.

Install: python -m pip install pymupdf
Run:     python extract_aspice.py --pdf Automotive-SPICE-PAM-v41.pdf --out ASPICE_Processes.md

The PDF must be text-searchable and use the v4.1 chapter 4 table structure.
This script is for working with a legitimately obtained copy of the PAM;
observe the source publisher's restrictions on redistribution.
"""
from __future__ import annotations

import argparse
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

PROCESS_IDS = [
    "ACQ.4", "SPL.2", "SYS.1", "SYS.2", "SYS.3", "SYS.4", "SYS.5",
    "VAL.1", "SWE.1", "SWE.2", "SWE.3", "SWE.4", "SWE.5", "SWE.6",
    "SUP.1", "SUP.8", "SUP.9", "SUP.10", "MAN.3", "MAN.5", "MAN.6",
    "PIM.3", "REU.2",
]

# Matches chapter-4 process headings, but not table rows or the TOC.
HEADING_RE = re.compile(
    r"^\s*4\.\d+\.\d+\.?\s+([A-Z]{3}\.\d+)\s+(.+?)\s*$"
)
OUTCOME_RE = re.compile(r"(?m)^\s*(\d+)\)\s*")
II_RE = re.compile(r"^\s*(\d{2}-\d{2})\s+(.+?)\s*$", re.S)
BP_ROW_RE = re.compile(r"^\s*BP\s*(\d+)\s*:?[ .-]?\s*", re.I)


@dataclass
class Section:
    pid: str
    page: int  # zero-based
    y: float
    heading: str


@dataclass
class SavedRow:
    cells: list


@dataclass
class SavedTable:
    """Freeze table data immediately: PyMuPDF tables depend on live page state."""
    bbox: tuple
    rows: list[SavedRow]
    values: list[list[str | None]]

    def extract(self):
        return self.values


def save_tables(page) -> list[SavedTable]:
    items = []
    for table in page.find_tables().tables:
        items.append(SavedTable(tuple(table.bbox),
                                [SavedRow(list(row.cells)) for row in table.rows],
                                [list(row) for row in table.extract()]))
    return items


@dataclass
class Process:
    pid: str
    name: str
    purpose: str
    outcomes: OrderedDict[int, str]
    bps: OrderedDict[int, str]
    outcome_iis: dict[int, OrderedDict[str, str]] = field(default_factory=dict)
    outcome_bps: dict[int, set[int]] = field(default_factory=dict)
    source_pages: tuple[int, int] = (0, 0)


def clean_lines(text: str) -> str:
    """Remove PDF soft wraps, but retain bullets, notes and new paragraphs."""
    out: list[str] = []
    para = ""
    for original in text.splitlines():
        line = re.sub(r"\s+", " ", original).strip()
        if not line:
            if para:
                out.append(para)
                para = ""
            continue
        is_special = bool(re.match(r"(?:[•●▪\-] |(?:NOTE|Note)\s*\d+\s*:)", line))
        if is_special:
            if para:
                out.append(para)
                para = ""
            para = line
        elif para and re.match(r"(?:[•●▪\-] |(?:NOTE|Note)\s*\d+\s*:)", para):
            # Continuation of an indented bullet or Note is part of the same item.
            para += " " + line
        elif para:
            # PDF line-wraps in the middle of sentences.
            para += " " + line
        else:
            para = line
    if para:
        out.append(para)
    return "\n\n".join(out)


def find_sections(pdf: fitz.Document) -> list[Section]:
    found: list[Section] = []
    # Chapter 4 is pages 29-98 in the supplied v4.1 model.
    for pno in range(28, min(len(pdf), 99)):
        page = pdf[pno]
        blocks = page.get_text("dict", sort=True)["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                value = "".join(s["text"] for s in line["spans"]).strip()
                match = HEADING_RE.match(value)
                if match:
                    found.append(Section(match[1], pno, line["bbox"][1], match[2]))
    found.sort(key=lambda s: (s.page, s.y))
    return found


def process_text(pdf: fitz.Document, start: Section, matrix_page: int, matrix_y: float) -> str:
    texts = []
    for pno in range(start.page, matrix_page + 1):
        page = pdf[pno]
        y0 = max(70, start.y - 2) if pno == start.page else 75
        y1 = min(matrix_y - 1.5, 740) if pno == matrix_page else 740
        if y0 < y1:
            texts.append(page.get_text("text", sort=True,
                                       clip=fitz.Rect(58, y0, 542, y1)))
    return "\n".join(texts)


def field_between(content: str, beginning: str, ending: str) -> str:
    match = re.search(
        rf"(?m)^\s*{re.escape(beginning)}\s*$([\s\S]*?)(?=^\s*{re.escape(ending)}\s*$)",
        content,
    )
    if not match:
        raise ValueError(f"Unable to find section {beginning!r} followed by {ending!r}")
    return match.group(1).strip()


def parse_outcomes(text: str) -> OrderedDict[int, str]:
    markers = list(OUTCOME_RE.finditer(text))
    result: OrderedDict[int, str] = OrderedDict()
    for i, match in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        result[int(match[1])] = clean_lines(text[match.end():end])
    return result


def parse_bps(text: str, pid: str) -> OrderedDict[int, str]:
    # The v4.1 PDF has a source typo "SPL2.BP7", hence the alternative.
    id_pat = re.escape(pid)
    alt = "SPL2" if pid == "SPL.2" else "(?!)"
    marker = re.compile(rf"(?m)^\s*(?:{id_pat}|{alt})\.BP\s*(\d+)\s*:\s*")
    matches = list(marker.finditer(text))
    bps: OrderedDict[int, str] = OrderedDict()
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        bps[int(match[1])] = clean_lines(text[match.end():end])
    return bps


def table_rows(table) -> list[tuple[str, list[float]]]:
    """Return row label and x centers of X marks, using PDF cell geometry."""
    values = table.extract()
    result: list[tuple[str, list[float]]] = []
    for row, strings in zip(table.rows, values):
        labels: list[str] = []
        xs: list[float] = []
        for bbox, value in zip(row.cells, strings):
            if bbox is None or not value or not value.strip():
                continue
            token = value.strip()
            if token == "X":
                xs.append((bbox[0] + bbox[2]) / 2)
            elif bbox[0] < 380 or (bbox[2] < 380):
                labels.append(token)
            elif token.startswith("Output Information Items") or token.startswith("Base Practices"):
                labels.append(token)
            # Table title and outcome column labels are ignored here.
        result.append((" ".join(labels).strip(), xs))
    return result


def is_matrix_header(pid: str, table) -> bool:
    rows = table.extract()
    if not rows:
        return False
    first = [x or "" for x in rows[0]]
    return any(re.match(rf"^{re.escape(pid)}\s+", x) for x in first) and any(
        re.search(r"Outcome\s+\d+", x) for x in first
    )


def get_outcome_centers(table) -> dict[int, float]:
    result = {}
    for value, cell in zip(table.extract()[0], table.rows[0].cells):
        if not value or cell is None:
            continue
        match = re.search(r"Outcome\s*(\d+)", value)
        if match:
            result[int(match[1])] = (cell[0] + cell[2]) / 2
    return result


def process_table_mapping(
    pdf: fitz.Document,
    pid: str,
    start: Section,
    next_section: Section | None,
    tables_by_page: dict[int, list],
) -> tuple[int, float, dict[int, OrderedDict[str, str]], dict[int, set[int]]]:
    # Identify the exact top of the process's mapping table.
    first: tuple[int, object] | None = None
    last_p = next_section.page if next_section else min(len(pdf) - 1, 98)
    for pno in range(start.page, last_p + 1):
        for t in tables_by_page.get(pno, []):
            if is_matrix_header(pid, t):
                first = (pno, t)
                break
        if first:
            break
    if first is None:
        raise ValueError(f"{pid}: no outcome-mapping table found")
    first_page, head_table = first
    centers = get_outcome_centers(head_table)
    if not centers:
        raise ValueError(f"{pid}: cannot locate outcome columns")
    oi_map: dict[int, OrderedDict[str, str]] = {k: OrderedDict() for k in centers}
    bp_map: dict[int, set[int]] = {k: set() for k in centers}

    mode = None
    # On some pages the table continues without repeating the outcome header.
    for pno in range(first_page, last_p + 1):
        for table in sorted(tables_by_page.get(pno, []), key=lambda t: t.bbox[1]):
            if pno == first_page and table.bbox[1] < head_table.bbox[1] - 1:
                continue
            if next_section and pno == next_section.page and table.bbox[1] >= next_section.y:
                continue
            if pno == first_page and table is not head_table and table.bbox[1] < head_table.bbox[1] + 1:
                continue
            if not any(v == "X" for row in table.extract() for v in row):
                continue
            # No other process's matrix may be included in this interval.
            if pno != first_page and any(
                (re.match(r"^[A-Z]{3}\.\d+\s+", v or "") and "Outcome" in str(table.extract()[0]))
                for v in table.extract()[0]
            ):
                continue
            for label, xcoords in table_rows(table):
                compact = re.sub(r"\s+", " ", label).strip()
                if re.search(r"Output Information Items?", compact, re.I):
                    mode = "ii"
                    continue
                if re.search(r"Base Practices", compact, re.I):
                    mode = "bp"
                    continue
                if mode is None or not xcoords:
                    continue
                indexes = {min(centers, key=lambda i: abs(centers[i] - x)) for x in xcoords}
                if mode == "ii":
                    match = II_RE.match(compact)
                    if not match:
                        continue
                    code, name = match.groups()
                    for idx in indexes:
                        oi_map[idx][code] = name
                elif mode == "bp":
                    match = BP_ROW_RE.match(compact)
                    if not match:
                        continue
                    for idx in indexes:
                        bp_map[idx].add(int(match[1]))
    return first_page, head_table.bbox[1], oi_map, bp_map


def parse_process(
    pdf: fitz.Document,
    start: Section,
    end: Section | None,
    tables_by_page: dict[int, list],
) -> Process:
    mp, my, ii_map, bp_map = process_table_mapping(
        pdf, start.pid, start, end, tables_by_page
    )
    raw = process_text(pdf, start, mp, my)
    name = clean_lines(field_between(raw, "Process name", "Process purpose"))
    purpose = clean_lines(field_between(raw, "Process purpose", "Process outcomes"))
    outcomes = parse_outcomes(field_between(raw, "Process outcomes", "Base Practices"))
    bp_section = raw.split("Base Practices", 1)[1]
    bps = parse_bps(bp_section, start.pid)
    if not outcomes or not bps:
        raise ValueError(f"{start.pid}: no outcomes or no BPs parsed")
    if set(outcomes) != set(ii_map) or set(outcomes) != set(bp_map):
        raise ValueError(
            f"{start.pid}: outcome numbers mismatch: text={list(outcomes)}, "
            f"table={list(ii_map)}"
        )
    for index, refs in bp_map.items():
        missing = refs - set(bps)
        if missing:
            raise ValueError(f"{start.pid}: outcome {index} references missing BPs {missing}")
    if not all(bp_map.values()):
        raise ValueError(f"{start.pid}: one or more outcomes lack BP mapping")
    last_page = end.page if end else mp
    return Process(start.pid, name, purpose, outcomes, bps, ii_map, bp_map,
                   source_pages=(start.page + 1, max(mp + 1, last_page)))


def bp_title_and_body(raw: str) -> tuple[str, str]:
    # Keep all paragraphs and notes, while making the leading activity a heading.
    first, *rest = raw.split("\n\n")
    parts = re.split(r"(?<=\.)\s+(?=[A-Z])", first, maxsplit=1)
    if len(parts) == 2:
        title, body = parts
    else:
        title, body = first, ""
    details = "\n\n".join(([body] if body else []) + rest)
    return title.rstrip(". "), details


def to_markdown(p: Process) -> str:
    output = [f"# {p.pid} - {p.name}", "", "## Process purpose", "", p.purpose,
              "", "## Process outcomes", ""]
    for n, text in p.outcomes.items():
        output += [f"### Outcome {n}", "", text, "", "#### Output Information Items", ""]
        items = p.outcome_iis[n]
        output.extend(f"- **{code}** — {title}" for code, title in items.items())
        if not items:
            output.append("- _No Output Information Item mapped to this outcome in the PAM table._")
        output += ["", "#### Base Practices", ""]
        for number in sorted(p.outcome_bps[n]):
            title, _ = bp_title_and_body(p.bps[number])
            output.append(f"- **{p.pid}.BP{number}** — {title}")
        output.append("")
    output += ["## Base Practices", ""]
    for n, raw in p.bps.items():
        title, body = bp_title_and_body(raw)
        output += [f"### BP{n} - {title}", ""]
        if body:
            output += [body, ""]
    return "\n".join(output).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path,
                        default=Path("Automotive-SPICE-PAM-v41.pdf"))
    parser.add_argument("--out", type=Path, default=Path("ASPICE_Processes.md"))
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")
    with fitz.open(args.pdf) as pdf:
        sections = find_sections(pdf)
        indices = {s.pid: i for i, s in enumerate(sections)}
        missing = set(PROCESS_IDS) - set(indices)
        if missing:
            raise RuntimeError(f"Missing process section headings: {sorted(missing)}")
        pages = range(min(s.page for s in sections), max(s.page for s in sections) + 2)
        tables_by_page = {p: save_tables(pdf[p]) for p in pages if p < len(pdf)}
        chunks = []
        for pid in PROCESS_IDS:
            i = indices[pid]
            start = sections[i]
            end = sections[i + 1] if i + 1 < len(sections) else None
            process = parse_process(pdf, start, end, tables_by_page)
            chunks.append(to_markdown(process))
            total_ii = sum(len(x) for x in process.outcome_iis.values())
            total_bp = sum(len(x) for x in process.outcome_bps.values())
            print(f"{pid:<7} {len(process.outcomes):2} outcomes, "
                  f"{len(process.bps):2} BPs, {total_ii:2} II links, "
                  f"{total_bp:2} BP links")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n---\n\n".join(chunks), encoding="utf-8")
    print(f"\nSaved {len(chunks)} processes to {args.out.resolve()}")


if __name__ == "__main__":
    main()
