"""The security policy forbids inline scripts (worker/policy.js): every page script must be a file, and no markup or
script may use inline event handlers (onclick=, onerror=, ...) or javascript: links. Only the prerender hints
(<script type="speculationrules">) may stay inline."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "web").glob("*.html"))
SCRIPTS = sorted((ROOT / "web" / "assets").glob("*.js")) + sorted((ROOT / "web" / "species").glob("*.js"))
HANDLER = re.compile(r"""<[a-z][^>]*\son[a-z]+\s*=\s*["'\\]""", re.I)


def test_no_inline_script_blocks():
    for p in PAGES:
        s = p.read_text()
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", s, re.S | re.I):
            attrs, body = m.group(1), m.group(2)
            if "src=" in attrs or 'type="speculationrules"' in attrs:
                continue
            assert not body.strip(), f"{p.name}: inline script (move it into a file under web/assets/): {body.strip()[:60]!r}"


def test_no_inline_event_handlers_or_javascript_links():
    for p in PAGES + SCRIPTS:
        s = p.read_text()
        assert not HANDLER.search(s), f"{p.name}: inline event handler {HANDLER.search(s).group(0)[:80]!r}"
        assert "javascript:" not in s, f"{p.name}: javascript: link"


def test_policy_has_no_unsafe_inline_for_scripts():
    pol = (ROOT / "worker" / "policy.js").read_text()
    script_src = re.search(r'"script-src ([^"]*)"', pol).group(1)
    assert "'unsafe-inline'" not in script_src and "'unsafe-eval'" not in script_src
