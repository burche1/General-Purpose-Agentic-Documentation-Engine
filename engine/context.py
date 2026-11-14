"""Read human-authored Markdown context without reading project source documents."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

MAX_CONTEXT_BYTES = 256_000
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class ProjectContext:
    project_dir: Path
    file_path: Path
    raw: str
    sha256: str
    title: str
    sections: dict[str, str]

    def content(self, *names: str) -> str:
        """Retrieve first nonempty matching section; aliases are accepted."""
        for name in names:
            value = self.sections.get(normalize(name), "").strip()
            if value:
                return value
        return ""


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def parse_context(project_dir: Path) -> ProjectContext:
    project_dir = project_dir.expanduser().resolve(strict=True)
    if not project_dir.is_dir():
        raise ValueError(f"Not a project directory: {project_dir}")
    source = project_dir / "context.md"
    if not source.is_file():
        raise FileNotFoundError(f"Expected {source}. Create a context.md in the project root.")
    # Prevent a symlinked context from reaching outside the selected project.
    if not source.resolve().is_relative_to(project_dir):
        raise ValueError("context.md must remain within the project directory")
    raw_bytes = source.read_bytes()
    if len(raw_bytes) > MAX_CONTEXT_BYTES:
        raise ValueError(f"context.md is too large (> {MAX_CONTEXT_BYTES} bytes)")
    raw = raw_bytes.decode("utf-8-sig")
    if not raw.strip():
        raise ValueError("context.md is empty")

    title = project_dir.name
    sections: dict[str, list[str]] = {}
    current = "introduction"
    sections[current] = []
    inside_fence = False
    for line in raw.splitlines():
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
        match = None if inside_fence else HEADING.match(line)
        if match:
            level, heading = match.groups()
            if len(level) == 1 and title == project_dir.name:
                title = heading.strip()
            # Treat second-level headings as primary sections, keep deeper headings in body.
            if len(level) <= 2:
                current = normalize(heading)
                sections.setdefault(current, [])
                continue
        sections[current].append(line)
    merged = {key: "\n".join(lines).strip() for key, lines in sections.items()}
    project_section = merged.get("project", "")
    name_match = re.search(r"(?im)^\s*(?:\*\*)?name(?:\*\*)?\s*:\s*(.+)$", project_section)
    if name_match:
        title = name_match.group(1).strip().strip("*`")
    return ProjectContext(
        project_dir=project_dir,
        file_path=source,
        raw=raw,
        sha256=sha256(raw_bytes).hexdigest(),
        title=title,
        sections=merged,
    )


def lines_as_items(text: str) -> list[str]:
    """Extract requested deliverables/criteria from Markdown bullets and simple prose."""
    items: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s*)", "", line)
        line = line.strip()
        if line:
            items.append(line)
    return items
