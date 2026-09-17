#!/usr/bin/env python3
"""Build the LoRA training ebook HTML from the Webflow blog collection."""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTION_ID = "693a85f0dc4ce6791e56dd23"
CHAPTERS = [
    {"id": "ch1", "slug": "when-to-train-a-lora"},
    {"id": "ch2", "slug": "decide-what-to-train-lora"},
    {"id": "ch3", "slug": "build-the-dataset-lora"},
    {"id": "ch4", "slug": "set-up-the-training-run-lora"},
    {"id": "ch5", "slug": "run-and-monitor-lora-training"},
    {"id": "ch6", "slug": "control-loras-ic-lora"},
]
# Chapter covers whose footage reads better mirrored (per the Figma draft).
FLIPPED_COVERS = {"ch6"}
# Override the default assets/chapterN.mp4 path when a chapter has a later cut.
COVER_VIDEOS = {"ch2": "assets/chapter2-upd.mp4"}
# Chapters that ship a second cut for phones. CSS shows one of the pair at a
# time and setupCoverVideos pauses whichever is hidden.
MOBILE_COVERS = {"ch2": {"src": "assets/hero.mp4", "poster": "assets/hero-poster.jpg"}}

LTX_HOME_URL = "https://ltx.io/"
LTX_TRY_NOW_URL = "https://app.ltx.io/"
LTX_SALES_URL = (
    "https://ltx.io/forms/ltx-contact-sales?kpi=licensing&placement=lora-training-guide"
)


def nav_ctas_html(prefix: str) -> str:
    buttons = f"""          <a class="ltx-btn ltx-btn--primary" href="{LTX_SALES_URL}" target="_blank" rel="noopener noreferrer">Talk to Sales</a>
          <a class="ltx-btn ltx-btn--secondary" href="{LTX_TRY_NOW_URL}" target="_blank" rel="noopener noreferrer">Try Now</a>"""
    if prefix == "rail":
        return f"""        <div class="rail__ctas">
          <p class="rail__ctas-lead heading-style-h3">Questions? We&rsquo;re happy to help.</p>
          <div class="rail__ctas-actions nav-ctas">
{buttons}
          </div>
        </div>"""
    return f"""        <div class="{prefix}__ctas nav-ctas">
{buttons}
        </div>"""


def asset_version(name: str) -> str:
    """Short content hash appended to local asset URLs.

    GitHub Pages serves styles.css with a 10-minute max-age and no fingerprint,
    so phones keep showing an old stylesheet long after a deploy. Keying the URL
    to the file's contents makes a changed file a different URL.
    """
    path = ROOT / name
    if not path.exists():
        return "0"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def load_token() -> str:
    env = ROOT / ".env"
    token = os.environ.get("WEBFLOW_API_TOKEN")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("WEBFLOW_API_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not token:
        raise SystemExit("WEBFLOW_API_TOKEN missing")
    return token


def api_get(token: str, url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "accept": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


PROTECTED_WORDS = {
    "lora": "LoRA",
    "ic-lora": "IC-LoRA",
    "ic-loras": "IC-LoRAs",
    "ltx": "LTX",
    "tl;dr": "TL;DR",
    "tldr": "TL;DR",
}
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9’';\-]*")


def _cased_word(word: str) -> str:
    key = word.lower()
    if key in PROTECTED_WORDS:
        return PROTECTED_WORDS[key]
    return word.lower()


def sentence_case(text: str) -> str:
    """Title Case → sentence case, keeping LoRA / IC-LoRA / LTX intact."""
    if not text:
        return text
    cased = WORD_RE.sub(lambda m: _cased_word(m.group(0)), text)
    for i, ch in enumerate(cased):
        if ch.isalpha():
            return cased[:i] + ch.upper() + cased[i + 1 :]
    return cased


_ARTICLE_RE = re.compile(r"\b(an?|the)(\s+)(?=\S)", re.I)


def glue_articles(text: str) -> str:
    """Bind articles to the next word with a nbsp so they never end a wrapped line."""
    return _ARTICLE_RE.sub(lambda m: f"{m.group(1)}\u00a0", text)


def sentence_case_html(html: str) -> str:
    first = True
    parts: list[str] = []
    for part in re.split(r"(<[^>]+>)", html):
        if part.startswith("<"):
            parts.append(part)
            continue
        if first and WORD_RE.search(part):
            parts.append(sentence_case(part))
            first = False
        else:
            parts.append(WORD_RE.sub(lambda m: _cased_word(m.group(0)), part))
    return "".join(parts)


def slugify(text: str) -> str:
    text = html_lib.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[’']", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "section"


# Same copy glyph used by the BibTeX block on ltx.io publication pages.
COPY_SVG = (
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"'
    ' stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<rect x="8" y="8" width="13" height="13" rx="2.5"></rect>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>'
    "</svg>"
)
CHECK_SVG = (
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"'
    ' stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M5 12.5 10 17.5 19 6.5"></path>'
    "</svg>"
)


# Blog-series footers ("Previous: … Next: …"). The ebook has its own navigation,
# so these paragraphs are dropped rather than rewritten.
NAV_LABEL = re.compile(
    r"^(next in series|next|previous|prev|start from the beginning|first|read next)$",
    re.I,
)


def is_nav_paragraph(inner: str) -> bool:
    if "<a" not in inner.lower():
        return False
    rest = re.sub(r"<a\b[^>]*>.*?</a>", " ", inner, flags=re.I | re.S)
    rest = html_lib.unescape(re.sub(r"<[^>]+>", " ", rest)).replace("\u00a0", " ")
    rest = re.sub(r"\s+", " ", rest).strip()
    if not rest:
        return False
    parts = [p.strip(" :.,\u2013\u2014-\u200d") for p in re.split(r"[:\u00b7|/]", rest)]
    parts = [p for p in parts if p]
    return bool(parts) and all(NAV_LABEL.match(p) for p in parts)


# Spacer paragraphs and line-break padding the Webflow editor leaves behind when
# copy is reflowed: <p></p>, <p>&nbsp;</p>, <p><br></p>, "…text.<br><br></p>".
BLANK_P = re.compile(r"<p\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>", re.I)
TRAILING_BR = re.compile(r"(?:<br\s*/?>\s*)+(?=</p>)", re.I)


class SimpleRewriter:
    def __init__(self, chapter_id: str, slug_to_chapter: dict[str, str]):
        self.chapter_id = chapter_id
        self.slug_to_chapter = slug_to_chapter
        self.h2s: list[tuple[str, str]] = []
        self.stripped_nav = 0
        self.stripped_blanks = 0
        self._used: dict[str, int] = {}

    def _sid(self, text: str) -> str:
        sid = slugify(text)
        n = self._used.get(sid, 0)
        self._used[sid] = n + 1
        return f"{sid}-{n + 1}" if n else sid

    def rewrite_hrefs(self, html: str) -> str:
        def repl(m: re.Match[str]) -> str:
            href = m.group(1)
            path = urllib.parse.urlparse(href).path
            sm = re.search(r"/blog/([a-z0-9-]+)/?$", path)
            if sm:
                ch = self.slug_to_chapter.get(sm.group(1))
                if ch:
                    return f'href="#{ch}"'
            return m.group(0)

        return re.sub(r'href="([^"]+)"', repl, html)

    def open_external_in_new_tab(self, html: str) -> str:
        def repl(m: re.Match[str]) -> str:
            tag = m.group(0)
            href = m.group(1) or ""
            if href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
                return tag
            if re.search(r"\btarget=", tag, re.I):
                tag = re.sub(r'\btarget="[^"]*"', 'target="_blank"', tag, count=1, flags=re.I)
            else:
                tag = tag[:-1] + ' target="_blank">'
            if re.search(r"\brel=", tag, re.I):
                tag = re.sub(r'\brel="[^"]*"', 'rel="noopener noreferrer"', tag, count=1, flags=re.I)
            else:
                tag = tag[:-1] + ' rel="noopener noreferrer">'
            return tag

        return re.sub(r'<a\b[^>]*\bhref="([^"]*)"[^>]*>', repl, html, flags=re.I)

    def rewrite_code_blocks(self, html: str) -> str:
        def repl(m: re.Match[str]) -> str:
            body = m.group(1)
            return (
                '<div class="code-card">'
                '<button class="code-card__copy" type="button" aria-label="Copy code"'
                f" data-copy-code>{COPY_SVG}</button>"
                f'<pre class="code-card__body">{body}</pre>'
                "</div>"
            )

        return re.sub(r"<pre[^>]*>([\s\S]*?)</pre>", repl, html, flags=re.I)

    def strip_series_nav(self, html: str) -> str:
        def repl(m: re.Match[str]) -> str:
            if is_nav_paragraph(m.group(1)):
                self.stripped_nav += 1
                return ""
            return m.group(0)

        return re.sub(r"<p[^>]*>((?:(?!</p>)[\s\S])*?)</p>", repl, html, flags=re.I)

    def strip_blank_blocks(self, html: str) -> str:
        """Drop spacer paragraphs and trailing <br>s; keep breaks inside code."""

        def clean(chunk: str) -> str:
            chunk, n = BLANK_P.subn("", chunk)
            self.stripped_blanks += n
            chunk, n = TRAILING_BR.subn("", chunk)
            self.stripped_blanks += n
            return chunk

        return "".join(
            piece if _PROTECTED_BLOCK.fullmatch(piece) else clean(piece)
            for piece in _PROTECTED_BLOCK.split(html)
        )

    def rewrite(self, html: str) -> str:
        html = self.rewrite_hrefs(html)
        html = self.open_external_in_new_tab(html)
        html = html.replace('alt="__wf_reserved_inherit"', 'alt=""')
        html = self.strip_series_nav(html)
        html = self.strip_blank_blocks(html)
        html = self.rewrite_code_blocks(html)

        def h2repl(m: re.Match[str]) -> str:
            inner = sentence_case_html(m.group(1))
            text = re.sub(r"<[^>]+>", "", inner)
            text = html_lib.unescape(re.sub(r"\s+", " ", text)).strip()
            sid = f"{self.chapter_id}-{self._sid(text)}"
            self.h2s.append((sid, text))
            return (
                f'<h2 class="heading-style-h2" id="{html_lib.escape(sid)}" data-section'
                f' data-chapter="{self.chapter_id}">{inner}</h2>'
            )

        def h3repl(m: re.Match[str]) -> str:
            return f'<h3 class="heading-style-h3">{sentence_case_html(m.group(1))}</h3>'

        html = re.sub(r"<h2>(.*?)</h2>", h2repl, html, flags=re.I | re.S)
        html = re.sub(r"<h3>(.*?)</h3>", h3repl, html, flags=re.I | re.S)
        html = re.sub(r"<h4>", '<h4 class="heading-style-h4">', html, flags=re.I)
        return html


def fetch_item(token: str, slug: str) -> dict:
    q = urllib.parse.urlencode({"slug": slug, "limit": 1})
    data = api_get(token, f"https://api.webflow.com/v2/collections/{COLLECTION_ID}/items?{q}")
    items = data.get("items") or []
    if not items:
        raise SystemExit(f"Missing CMS item: {slug}")
    return items[0]


def cover_url(fd: dict) -> str:
    cover = fd.get("cover")
    if isinstance(cover, dict):
        return cover.get("url") or ""
    return ""


def strip_tags(html: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", html or "")).strip()


# Runs of regular spaces, NBSP, and/or &nbsp; — Webflow often stores "word.  Next".
_SPACE_RUN = re.compile(r"(?:[ \t\u00a0]|&nbsp;){2,}")
_PROTECTED_BLOCK = re.compile(
    r"(<(?:pre|code)\b[^>]*>[\s\S]*?</(?:pre|code)>|"
    r'<div class="code-card">[\s\S]*?</div>)',
    re.I,
)


def collapse_space_runs(text: str, stats: dict | None = None) -> str:
    """Collapse 2+ spaces in a text node. Indent-only nodes (between tags) are unchanged."""
    if not text or not text.strip():
        return text

    def repl(m: re.Match[str]) -> str:
        if stats is not None:
            stats["count"] = stats.get("count", 0) + 1
            examples = stats.setdefault("examples", [])
            if len(examples) < 8:
                start = max(0, m.start() - 36)
                end = min(len(text), m.end() + 36)
                examples.append(text[start:end].replace("\n", " "))
        return " "

    return _SPACE_RUN.sub(repl, text)


def collapse_copy_spaces(html: str, stats: dict | None = None) -> str:
    """Collapse extra spaces in copy text; leave tags, pre, code, and code-cards alone."""
    if not html:
        return html

    def collapse_unprotected(chunk: str) -> str:
        parts = re.split(r"(<[^>]+>)", chunk)
        return "".join(
            part if part.startswith("<") else collapse_space_runs(part, stats) for part in parts
        )

    pieces = _PROTECTED_BLOCK.split(html)
    out: list[str] = []
    for piece in pieces:
        if _PROTECTED_BLOCK.fullmatch(piece):
            out.append(piece)
        else:
            out.append(collapse_unprotected(piece))
    return "".join(out)


def nav_items_html(chapters: list[dict], kind: str) -> str:
    bits = []
    for ch in chapters:
        num = ch["id"].replace("ch", "").zfill(2)
        subs = ""
        if kind == "rail":
            lis = "".join(
                f'<li><a class="rail__section" href="#{sid}" data-section-link="{sid}">{html_lib.escape(title)}</a></li>'
                for sid, title in ch["h2s"]
            )
            bits.append(
                f'''<li class="rail__item" data-chapter="{ch["id"]}">
  <div class="rail__row">
    <a class="rail__chapter" href="#{ch["id"]}" data-chapter-link="{ch["id"]}">
      <span class="rail__num">{num}</span>
      <span class="rail__chapter-title">{html_lib.escape(ch["name"])}</span>
    </a>
    <div class="rail__sections">
      <ul class="rail__sections-list" aria-label="{html_lib.escape(ch["name"])} sections">{lis}</ul>
    </div>
    <span class="rail__progress" aria-hidden="true"></span>
  </div>
</li>'''
            )
        elif kind == "mh":
            lis = "".join(
                f'<li><a class="mh__section" href="#{sid}" data-mh-link>{html_lib.escape(title)}</a></li>'
                for sid, title in ch["h2s"]
            )
            bits.append(
                f'''<li class="mh__item" data-mh-item="{ch["id"]}">
  <div class="mh__row">
    <a class="mh__link" href="#{ch["id"]}" data-mh-link>
      <span class="mh__num">{num}</span>
      <span class="mh__title">{html_lib.escape(ch["name"])}</span>
    </a>
    <button class="mh__expand" type="button" aria-label="Show sub-sections of {html_lib.escape(ch["name"])}" aria-expanded="false" aria-controls="mh-sub-{ch["id"]}" data-mh-expand="{ch["id"]}">
      <svg class="mh__chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"></path></svg>
    </button>
  </div>
  <div id="mh-sub-{ch["id"]}" class="mh__sections" aria-hidden="true" data-mh-sections="{ch["id"]}">
    <ul class="mh__sections-list">{lis}</ul>
  </div>
</li>'''
            )
        else:
            lis = "".join(
                f'<li><a href="#{sid}">{html_lib.escape(title)}</a></li>' for sid, title in ch["h2s"]
            )
            bits.append(
                f'''<li class="whats-inside__item">
  <details>
    <summary>
      <span class="whats-inside__num">{num}</span>
      <span class="whats-inside__title">{html_lib.escape(ch["name"])}</span>
      <span class="whats-inside__plus" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 8h12" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M8 2v12" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
      </span>
    </summary>
    <ul class="whats-inside__sections">{lis}</ul>
  </details>
</li>'''
            )
    return "\n".join(bits)


def chapter_html(ch: dict) -> str:
    num = ch["id"].replace("ch", "").zfill(2)
    syn = ch.get("synopsis") or ""
    syn_block = f'<div class="synopsis">{syn}</div>' if strip_tags(syn) else ""
    # The Webflow cover art doubles as the poster frame, so the card is never
    # empty while the footage loads.
    cover = ch.get("cover") or ""
    poster = f' poster="{html_lib.escape(cover)}"' if cover else ""
    flipped = " chapter__video--flipped" if ch["id"] in FLIPPED_COVERS else ""
    src = COVER_VIDEOS.get(ch["id"]) or f'assets/{ch["id"].replace("ch", "chapter")}.mp4'
    mobile = MOBILE_COVERS.get(ch["id"])
    variant = " chapter__video--desktop" if mobile else ""
    videos = f'''<video class="chapter__video{flipped}{variant}"{poster} autoplay muted loop playsinline
           preload="none" disablepictureinpicture aria-hidden="true" tabindex="-1" data-cover-video>
      <source src="{src}" type="video/mp4">
    </video>'''
    if mobile:
        mobile_poster = f' poster="{html_lib.escape(mobile["poster"])}"' if mobile.get("poster") else ""
        videos += f'''
    <video class="chapter__video{flipped} chapter__video--mobile"{mobile_poster} autoplay muted loop playsinline
           preload="none" disablepictureinpicture aria-hidden="true" tabindex="-1" data-cover-video>
      <source src="{mobile["src"]}" type="video/mp4">
    </video>'''
    return f'''<article id="{ch["id"]}" class="chapter">
  <header class="chapter__cover">
    {videos}
    <div class="chapter__scrim" aria-hidden="true"></div>
    <div class="chapter__cover-inner">
      <span class="chapter__pill">Chapter {num}</span>
      <h1 class="chapter__title heading-style-h2 text-balanced">{glue_articles(html_lib.escape(ch["name"]))}</h1>
    </div>
  </header>
  {syn_block}
  <div class="chapter__body rt">{ch["html"]}</div>
</article>'''


def page(chapters: list[dict]) -> str:
    first = chapters[0]
    intro = (first.get("meta") or "").strip() or (
        "A practical guide to deciding when a LoRA is worth training, "
        "what it should learn, how to build the dataset, and how to run, monitor, and ship it."
    )
    hero_lead = collapse_space_runs(
        f"When to train, what to learn, how to ship a LoRA on LTX. {intro}".strip()
    )
    # One sentence per line on desktop. CSS hides the breaks below 900px, where
    # the sentences run together as a single wrapping paragraph.
    hero_lead_html = ' <br class="hero__lead-break">'.join(
        html_lib.escape(sentence) for sentence in re.split(r"(?<=\.)\s+", hero_lead)
    )
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LoRA Training Guide | LTX</title>
  <meta name="description" content="{html_lib.escape(intro)}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="LoRA Training Guide | LTX">
  <meta property="og:description" content="{html_lib.escape(intro)}">
  <meta property="og:image" content="assets/lora-training-og.webp">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="LoRA Training Guide | LTX">
  <meta name="twitter:description" content="{html_lib.escape(intro)}">
  <meta name="twitter:image" content="assets/lora-training-og.webp">
  <meta name="theme-color" content="#e7e8eb">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
  <script src="https://use.typekit.net/emb1gsr.js"></script>
  <script>try{{Typekit.load()}}catch(e){{}}</script>
  <link rel="stylesheet" href="styles.css?v={asset_version("styles.css")}">
</head>
<body>
  <header class="mh" data-mobile-header>
    <div class="mh__bar">
      <a class="mh__logo" href="{LTX_HOME_URL}" aria-label="LTX">
        <img src="assets/ltx-logo-black.svg" alt="LTX" width="91" height="39">
      </a>
      <button class="mh__toggle" type="button" aria-label="Open chapter menu" aria-expanded="false" aria-controls="mh-drawer" data-mh-toggle>
        <span class="mh__toggle-icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
            <path class="mh__l1" d="M3 6h16" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"></path>
            <path class="mh__l2" d="M3 11h16" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"></path>
            <path class="mh__l3" d="M3 16h16" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"></path>
          </svg>
        </span>
      </button>
    </div>
    <div id="mh-drawer" class="mh__drawer" role="dialog" aria-label="Chapter menu" aria-hidden="true" data-mh-drawer>
      <nav>
        <ol class="mh__list">
          {nav_items_html(chapters, "mh")}
        </ol>
      </nav>
{nav_ctas_html("mh")}
    </div>
    <button class="mh__scrim" type="button" aria-label="Close chapter menu" tabindex="-1" data-mh-scrim></button>
  </header>

  <div class="page-stack container" id="top">
    <section class="hero" aria-label="LoRA training guide">
      <video class="hero__video hero__video--desktop" poster="assets/hero-poster.jpg" autoplay muted loop playsinline
             preload="metadata" disablepictureinpicture aria-hidden="true" tabindex="-1" data-cover-video>
        <source src="assets/hero.mp4" type="video/mp4">
      </video>
      <video class="hero__video hero__video--mobile" poster="assets/hero-poster-mobile.jpg" autoplay muted loop playsinline
             preload="none" disablepictureinpicture aria-hidden="true" tabindex="-1" data-cover-video>
        <source src="assets/hero-mobile.mp4" type="video/mp4">
      </video>
      <div class="hero__scrim" aria-hidden="true"></div>
      <div class="hero__inner">
        <a class="hero__logo" href="{LTX_HOME_URL}" aria-label="LTX">
          <img src="assets/ltx-logo-black.svg" alt="LTX" width="91" height="39">
        </a>
        <div class="hero__copy">
          <h1 class="hero__title h1-display">LoRA <br class="hero__break">training guide</h1>
          <p class="hero__lead text-balanced">{hero_lead_html}</p>
        </div>
      </div>
    </section>

    <div class="shell">
      <aside class="rail" aria-label="Table of contents">
        <div class="rail__inner">
          <a class="rail__logo" href="{LTX_HOME_URL}" aria-label="LTX">
            <img src="assets/ltx-logo-black.svg" alt="LTX" width="91" height="39">
          </a>
          <nav class="rail__nav">
            <ol class="rail__list">
              {nav_items_html(chapters, "rail")}
            </ol>
          </nav>
{nav_ctas_html("rail")}
        </div>
      </aside>

      <main class="content" id="content">
        <section class="whats-inside" aria-label="What's inside">
          <p class="whats-inside__eyebrow">What's inside</p>
          <ul class="whats-inside__list">
            {nav_items_html(chapters, "inside")}
          </ul>
        </section>
        {"".join(chapter_html(ch) for ch in chapters)}
        <p class="back-to-top"><a href="#top">Back to top</a></p>
      </main>
    </div>

    <footer class="ftr">
      <span>LTX · LoRA Training Guide</span>
      <span>© Lightricks. Content from the <a href="https://ltx.io/blog" target="_blank" rel="noopener noreferrer">LTX blog</a>.</span>
    </footer>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/lenis@1.3.26/dist/lenis.min.js"></script>
  <script src="app.js?v={asset_version("app.js")}"></script>
</body>
</html>
'''


def main() -> None:
    token = load_token()
    slug_to_chapter = {c["slug"]: c["id"] for c in CHAPTERS}
    space_stats: dict = {"count": 0, "examples": []}
    built = []
    for meta in CHAPTERS:
        item = fetch_item(token, meta["slug"])
        fd = item.get("fieldData") or {}
        rewriter = SimpleRewriter(meta["id"], slug_to_chapter)
        body = collapse_copy_spaces(rewriter.rewrite(fd.get("post-content") or ""), space_stats)
        synopsis = collapse_copy_spaces(
            rewriter.strip_blank_blocks(
                rewriter.strip_series_nav(
                    rewriter.open_external_in_new_tab(
                        rewriter.rewrite_hrefs(fd.get("synopsis") or "")
                    )
                )
            ),
            space_stats,
        )
        name = collapse_space_runs(sentence_case(fd.get("name") or meta["slug"]), space_stats)
        built.append(
            {
                **meta,
                "name": name,
                "synopsis": synopsis,
                "meta": collapse_space_runs(fd.get("post-meta-description") or "", space_stats),
                "cover": cover_url(fd),
                "html": body,
                "h2s": rewriter.h2s,
            }
        )
        print(
            f"OK {meta['id']} {fd.get('name')} "
            f"({len(rewriter.h2s)} h2, {rewriter.stripped_nav} nav lines removed, "
            f"{rewriter.stripped_blanks} blank blocks removed)"
        )
    out = ROOT / "index.html"
    out.write_text(page(built), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size} bytes)")
    print(f"Collapsed {space_stats['count']} extra space runs in copy")
    for ex in space_stats["examples"][:4]:
        print(f"  e.g. {ex!r}")


if __name__ == "__main__":
    main()
