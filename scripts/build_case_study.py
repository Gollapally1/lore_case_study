"""
Build a single self-contained HTML page that bundles the case-study artifact.

Reads the .md files in docs/ + README.md, weaves in screenshots from
docs/images/, and emits case_study.html at the repo root.

Open the HTML in a browser to view, or use the browser's "Print > Save as PDF"
to produce a PDF artifact for email — no pandoc / wkhtmltopdf toolchain
required, and Mermaid + syntax highlighting render correctly in both views.

Usage:
    python scripts/build_case_study.py
    # then open case_study.html in Chrome and File > Print > Save as PDF
"""
from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).parent.parent
DOCS = REPO / "docs"

# Order matters — this is the read-top-to-bottom narrative for the artifact.
SECTIONS = [
    ("Overview",                    REPO / "README.md"),
    ("Architecture",                DOCS / "ARCHITECTURE.md"),
    ("Requirements & Cost",         DOCS / "REQUIREMENTS.md"),
    ("Migration Plan",              DOCS / "MIGRATION_PLAN.md"),
    ("Adding a New Data Product",   DOCS / "HOWTO_NEW_DATA_PRODUCT.md"),
    ("Interview Talking Points",    DOCS / "TALKING_POINTS.md"),
]

# Optional: links displayed at the top of the artifact. Edit these before
# building the final version you ship.
LINKS = {
    "GitHub repo":      "https://github.com/<your-username>/lore_case_study",
    "Demo recording":   "https://www.loom.com/share/<your-loom-id>",
    "Live dashboard":   "http://localhost:8501 (after `streamlit run src/dashboard.py`)",
}


# ---------------------------------------------------------------------------
# A small, dependency-free Markdown -> HTML converter scoped to the subset
# of features the case-study docs actually use. Avoiding a runtime dep keeps
# the build step trivial (just python + stdlib).
# ---------------------------------------------------------------------------
def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_para: list[str] = []

    def flush_para():
        if in_para:
            joined = " ".join(in_para).strip()
            if joined:
                out.append(f"<p>{_inline(joined)}</p>")
            in_para.clear()

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        m = re.match(r"^```(\w+)?\s*$", line)
        if m:
            flush_para()
            lang = m.group(1) or "text"
            body: list[str] = []
            i += 1
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                body.append(lines[i])
                i += 1
            code = html.escape("\n".join(body))
            cls = f"language-{lang}"
            if lang == "mermaid":
                out.append(f'<div class="mermaid">{code}</div>')
            else:
                out.append(f'<pre><code class="{cls}">{code}</code></pre>')
            i += 1
            continue

        # ATX heading
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para()
            level = len(m.group(1))
            text = _inline(m.group(2).strip())
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # HR
        if re.match(r"^---+\s*$", line):
            flush_para()
            out.append("<hr/>")
            i += 1
            continue

        # Table (very lightweight: detect header / separator / row triplet)
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?[-]+", lines[i + 1]):
            flush_para()
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" +
                       "".join(f"<th>{_inline(c)}</th>" for c in header_cells) +
                       "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue

        # Lists
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if m:
            flush_para()
            ordered = bool(re.match(r"\d+\.", m.group(2)))
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>")
            while i < len(lines):
                m2 = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not m2:
                    if lines[i].strip() == "":
                        i += 1
                        continue
                    break
                out.append(f"<li>{_inline(m2.group(3).strip())}</li>")
                i += 1
            out.append(f"</{tag}>")
            continue

        # Blank line ends paragraph
        if line.strip() == "":
            flush_para()
            i += 1
            continue

        # Default: accumulate paragraph
        in_para.append(line.strip())
        i += 1

    flush_para()
    return "\n".join(out)


def _inline(text: str) -> str:
    # Inline code
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\b_([^_]+)_\b", r"<em>\1</em>", text)
    # Links [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>',
                  text)
    return text


# ---------------------------------------------------------------------------
# HTML shell — embedded CSS + CDN script tags for Mermaid + Prism.
# ---------------------------------------------------------------------------
HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lore Case Study — Strategic Pipeline Modernization</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/themes/prism.min.css">
<style>
  :root {
    --bg: #ffffff;
    --fg: #1a202c;
    --muted: #4a5568;
    --accent: #2b6cb0;
    --border: #e2e8f0;
    --code-bg: #f7fafc;
  }
  html { font-size: 16px; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: var(--fg);
    background: var(--bg);
    line-height: 1.6;
    max-width: 920px;
    margin: 0 auto;
    padding: 2.5rem 1.5rem 4rem;
  }
  header.cover {
    border-bottom: 1px solid var(--border);
    margin-bottom: 2.5rem;
    padding-bottom: 1.5rem;
  }
  header.cover h1 {
    font-size: 2.25rem;
    margin: 0 0 .25rem;
  }
  header.cover .subtitle {
    color: var(--muted);
    font-size: 1.05rem;
    margin: 0 0 1rem;
  }
  .meta { display: flex; flex-wrap: wrap; gap: 1.25rem; font-size: .9rem; color: var(--muted); }
  .meta a { color: var(--accent); text-decoration: none; }
  .meta a:hover { text-decoration: underline; }
  nav.toc {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem 1.25rem;
    margin: 2rem 0;
  }
  nav.toc h2 { margin: 0 0 .5rem; font-size: 1rem; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
  nav.toc ol { margin: 0; padding-left: 1.25rem; }
  nav.toc a { color: var(--accent); text-decoration: none; }
  nav.toc a:hover { text-decoration: underline; }
  section.doc {
    border-top: 1px solid var(--border);
    padding-top: 2rem;
    margin-top: 2.5rem;
  }
  section.doc:first-of-type { border-top: 0; padding-top: 0; margin-top: 0; }
  section.doc > h1 {
    font-size: 1.85rem;
    color: var(--accent);
    margin-top: 0;
  }
  h2 { font-size: 1.4rem; margin-top: 2rem; }
  h3 { font-size: 1.15rem; margin-top: 1.5rem; }
  p, ul, ol { margin: .75rem 0; }
  ul, ol { padding-left: 1.5rem; }
  code {
    font-family: "SF Mono", Monaco, Consolas, monospace;
    font-size: .9em;
    background: var(--code-bg);
    padding: .1em .35em;
    border-radius: 3px;
  }
  pre {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem;
    overflow-x: auto;
    font-size: .85rem;
    line-height: 1.5;
  }
  pre code { background: transparent; padding: 0; font-size: inherit; }
  blockquote {
    border-left: 4px solid var(--accent);
    margin: 1rem 0;
    padding: .25rem 1rem;
    color: var(--muted);
    background: var(--code-bg);
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin: 1rem 0;
    font-size: .92rem;
  }
  th, td {
    border: 1px solid var(--border);
    padding: .55rem .75rem;
    text-align: left;
    vertical-align: top;
  }
  th { background: var(--code-bg); font-weight: 600; }
  hr { border: 0; border-top: 1px solid var(--border); margin: 2rem 0; }
  a { color: var(--accent); }
  img { max-width: 100%; border: 1px solid var(--border); border-radius: 6px; }
  figure { margin: 1.25rem 0; }
  figcaption { font-size: .85rem; color: var(--muted); margin-top: .25rem; }
  .mermaid {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem;
    margin: 1rem 0;
    text-align: center;
  }
  .pdf-hint {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: 6px;
    padding: .75rem 1rem;
    margin-bottom: 1.5rem;
    font-size: .9rem;
  }
  @media print {
    .pdf-hint { display: none; }
    body { max-width: none; padding: 1rem; }
    section.doc { page-break-before: always; }
    section.doc:first-of-type { page-break-before: auto; }
    h1, h2, h3 { page-break-after: avoid; }
    pre, table, .mermaid, figure { page-break-inside: avoid; }
    a { color: var(--fg); text-decoration: none; }
    a[href^="http"]::after { content: " (" attr(href) ")"; font-size: .8em; color: var(--muted); }
  }
</style>
</head>
<body>
"""

FOOT = """
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default', securityLevel: 'loose' });</script>
<script src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-core.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
</body>
</html>
"""


def build() -> Path:
    out_path = REPO / "case_study.html"
    parts: list[str] = [HEAD]

    # Cover
    parts.append('<header class="cover">')
    parts.append('<h1>Lore Health — Strategic Pipeline Modernization</h1>')
    parts.append('<p class="subtitle">Case Study 1 · Staff Data Engineer Panel · '
                 'Naveen Gollapally</p>')
    parts.append('<div class="meta">')
    for label, url in LINKS.items():
        parts.append(f'<span><strong>{label}:</strong> '
                     f'<a href="{html.escape(url)}">{html.escape(url)}</a></span>')
    parts.append(f'<span><strong>Built:</strong> {date.today().isoformat()}</span>')
    parts.append('</div>')
    parts.append('</header>')

    parts.append(
        '<div class="pdf-hint"><strong>Tip:</strong> to produce a PDF, open this '
        'file in Chrome and choose File &rarr; Print &rarr; <em>Save as PDF</em>. '
        'Mermaid diagrams and syntax highlighting will render correctly. This box '
        'is hidden in the print/PDF output.</div>'
    )

    # TOC
    parts.append('<nav class="toc"><h2>Contents</h2><ol>')
    for title, _ in SECTIONS:
        anchor = title.lower().replace(" ", "-").replace("&", "and")
        parts.append(f'<li><a href="#{anchor}">{html.escape(title)}</a></li>')
    parts.append('</ol></nav>')

    # Sections
    for title, path in SECTIONS:
        anchor = title.lower().replace(" ", "-").replace("&", "and")
        parts.append(f'<section class="doc" id="{anchor}">')
        parts.append(f'<h1>{html.escape(title)}</h1>')
        if not path.exists():
            parts.append(f'<p><em>Missing: {path.relative_to(REPO)}</em></p>')
        else:
            md = path.read_text()
            # Strip the first H1 since the section header is the title.
            md = re.sub(r"^# .*\n", "", md, count=1)
            parts.append(md_to_html(md))
        parts.append('</section>')

    parts.append(FOOT)
    out_path.write_text("\n".join(parts))
    return out_path


if __name__ == "__main__":
    out = build()
    print(f"wrote {out.relative_to(REPO)} ({out.stat().st_size // 1024} KB)")
    print("open in Chrome -> File > Print > Save as PDF for the email attachment.")
