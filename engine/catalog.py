"""Execution capability registry. Stage 1 plans tasks; it does not run them."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    id: str
    title: str
    description: str


CATALOG: tuple[Capability, ...] = (
    Capability("inventory", "Inventory documents", "Identify sources, document roles, and versions."),
    Capability("extract", "Extract document content", "Parse and normalize source content and source locations."),
    Capability("retrieve", "Build local retrieval index", "Enable exact and semantic retrieval over local sources."),
    Capability("analyze", "Analyze documents", "Identify concepts, structures, responsibilities, and findings."),
    Capability("compare", "Compare documents and references", "Map evidence, differences, and contradictions."),
    Capability("gaps", "Identify gaps", "Separate missing information, conflicting evidence, and confirmed gaps."),
    Capability("consolidate", "Consolidate information", "Merge overlapping material while tracking its provenance."),
    Capability("design", "Design document structure", "Define the proposed outline and document interfaces."),
    Capability("generate", "Generate document drafts", "Produce output drafts from approved sources and structure."),
    Capability("validate", "Validate outputs", "Verify source support and stated quality criteria."),
    Capability("review", "Review and approve outputs", "Require a human decision before publication."),
    Capability("publish", "Publish local artifacts", "Write approved outputs under the local project folder."),
)
BY_ID = {cap.id: cap for cap in CATALOG}
ORDER = {cap.id: idx for idx, cap in enumerate(CATALOG)}


def choose_capabilities(raw: str, task_text: str) -> list[str]:
    """Heuristic baseline, useful without any model; sections are prioritized."""
    t = (task_text or raw).lower()
    selected = {"inventory", "extract", "analyze"}
    patterns = {
        "retrieve": ("search", "retrieve", "references", "reference material", "traceability", "citation"),
        "compare": ("compare", "against", "aligned with", "alignment", "consistency", "contradict", "differences", "versus"),
        "gaps": ("gap", "missing", "compliance", "incomplete", "shortcoming", "requirement coverage"),
        "consolidate": ("consolidat", "merge", "combine", "deduplicat", "unif", "overlap"),
        "design": ("design", "architecture", "structure", "outline", "propos", "organize", "restructur"),
        "generate": ("generat", "creat", "produc", "draft", "write", "improv", "rewrite", "deliver"),
    }
    for cap, tokens in patterns.items():
        if any(token in t for token in tokens):
            selected.add(cap)
    # Even summary-only jobs should produce a requested artifact. We use generate
    # when the objective asks for a report, summary, document, or output.
    if any(k in raw.lower() for k in ("output", "report", "summary", "document", "deliverable")):
        selected.add("generate")
    if "compare" in selected or "gaps" in selected:
        selected.add("retrieve")
    if "generate" in selected:
        selected.add("design")
    selected.update({"validate", "review", "publish"})
    return sorted(selected, key=lambda item: ORDER[item])
