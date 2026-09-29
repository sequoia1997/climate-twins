"""The public changelog: CHANGELOG.md in the repository, rendered to site/changelog.html by `ctw site`.

Write entries in plain language under a "## date" heading, newest first, below the <!-- entries --> marker.
Supported: ## and ### headings, "- " bullets, paragraphs, **bold**, *italic*, `code`, [links](url).
add_data_entry() is run by the yearly rebuild and records each data update once."""
from __future__ import annotations
import datetime as dt, html, json, re
from . import common as C

PATH = C.ROOT / "CHANGELOG.md"
MARK = "<!-- entries -->"


def _inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+|[\w./#-]+)\)", lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', t)
    return t


def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", t).lower()).strip("-")


def render(md: str) -> str:
    if MARK in md:                                                   # the lead paragraph is shown separately
        md = md.split(MARK, 1)[1]
    out, para, items = [], [], []

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>"); para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>"); items.clear()
    for line in md.splitlines():
        s = line.rstrip()
        if s.startswith("<!--") or s.startswith("# "):
            flush(); continue
        if s.startswith("## ") or s.startswith("### "):
            flush(); lvl = 2 if s.startswith("## ") else 3; txt = s[lvl + 1:].strip()
            out.append(f'<h{lvl} id="{_slug(txt)}">{_inline(txt)}</h{lvl}>'); continue
        if s.startswith("- "):
            if para: flush()
            items.append(s[2:].strip()); continue
        if s.startswith("  ") and items:
            items[-1] += " " + s.strip(); continue
        if not s:
            flush(); continue
        if items: flush()
        para.append(s.strip())
    flush()
    return "\n".join(out)


def intro(md: str) -> str:
    """The paragraph under the title, for the page's lead."""
    m = re.search(r"^# .*?\n\n(.+?)\n\n", md, re.S)
    return _inline(m.group(1).strip()) if m else ""


def add_data_entry(summary_path=None) -> bool:
    """Add a dated "Data update" entry for the build in site/data/summary.json, once per data version."""
    S = json.load(open(summary_path or (C.SITE / "data" / "summary.json")))
    ver = S["data_version"]
    md = PATH.read_text()
    tag = f"<!-- data:{ver} -->"
    if tag in md:
        return False
    day = dt.date.fromisoformat(ver)
    a, b = S["recent_years"]
    entry = (f"## {day.day} {day.strftime('%B %Y')}: data update\n{tag}\n\n"
             f"- **Rebuilt from the latest source data.** The \"already happening\" comparison now covers {a}–{b}.\n"
             f"- {len(S['places']):,} places, {S['n_models']} climate models"
             + (f", sea-level projections for {S['sealevel_places']} coastal places" if S.get("sealevel_places") else "") + ".\n\n")
    md = md.replace(MARK + "\n\n", MARK + "\n\n" + entry, 1) if MARK in md else md + "\n" + entry
    PATH.write_text(md)
    C.log.info("changelog: added the data update for %s", ver)
    return True
