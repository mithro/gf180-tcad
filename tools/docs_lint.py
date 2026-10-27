#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Vendored unchanged (below this header) from github.com/mithro/dot-claude, branch
# docs-writing-skill, commit e0dde9e99ba4d0f9d01bdabc8ac51ef87603825b,
# marketplace/docs-writing/skills/writing-docs/scripts/docs_lint.py
# (sha256 d0dedd0829489311d2738420f3b670cfe7216010c28fde3b59f854488f5b79ff of the original file).
# Copyright Tim Ansell; Apache License 2.0 (the LICENSE at the root of that branch).
# Update by copying the new upstream file below this header and changing the commit and sha256.
"""Check Markdown documentation pages against the writing-docs rules.

usage: uv run --no-project docs_lint.py [--no-front-matter] [--front-matter-keys type,owner,reader,review]
                                        [--max-links 15] FILE.md [FILE.md ...]

Fails (exit 1) on:
  - missing front matter, or a front matter without each required key (unless --no-front-matter);
  - a level-1 title over 65 characters;
  - a banned word or a forbidden phrase used in prose (a word set in `code` or inside "double quotes" is a
    mention, not a use, and is skipped; code fences and tables are skipped);
  - a sentence over 25 words, counted across wrapped lines;
  - a list with more than 7 items;
  - a heading deeper than five levels;
  - an image with no alt text, or alt text over 150 characters;
  - a how-to page (front matter `type: how-to`) whose level-2 headings are not exactly
    What you need, Steps, Check, If it fails, Next, in that order;
  - a callout (admonition) that contains a numbered step.
Warns (no failure) on: the watched words new / now / latest; a paragraph over 5 sentences; more than
--max-links links; more than two callouts; a page that is only links (unless its type is landing).

Markdown dialects: CommonMark, MyST (``` {directive} and ::: fences, % comments) and GitHub (> [!NOTE]).
"""
import argparse
import pathlib
import re
import sys

BANNED = ["just", "simply", "easy", "easily", "straightforward", "please note", "click here", "currently",
          "soon", "e.g.", "i.e.", "etc.", "in order to", "as of this writing"]
WATCH = ["new", "now", "latest"]
PHRASES = ["Future:", "Sources:", "unverified", "TODO", "not yet", "as read on"]
HOWTO_HEADINGS = ["What you need", "Steps", "Check", "If it fails", "Next"]
CALLOUT_DIRECTIVES = {"note", "warning", "tip", "important", "caution", "admonition", "hint", "danger",
                      "attention", "seealso", "error"}
LIST_ITEM = re.compile(r"^\s*(\d+[.)]|[-*+])\s+")
STEP_ITEM = re.compile(r"^\s*\d+[.)]\s+")
IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK = re.compile(r"(?<!!)\[[^\]]+\]\([^)]+\)")
DIRECTIVE = re.compile(r"^(```+|~~~+|:::+)\s*\{([a-zA-Z0-9_-]+)\}")
FENCE = re.compile(r"^(```+|~~~+|:::+)")


def words(s):
    return len(re.findall(r"[A-Za-z0-9'’`-]+", s))


def mentions_stripped(line):
    line = IMAGE.sub(" ", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)   # keep link text only
    line = re.sub(r"`[^`]*`", " X ", line)                 # code spans are mentions
    line = re.sub(r"\"[^\"]*\"", " X ", line)              # quoted spans are mentions
    line = re.sub(r"“[^”]*”", " X ", line)
    return line


class Page:
    def __init__(self, path, args):
        self.path = pathlib.Path(path)
        self.name = self.path.name
        self.args = args
        self.failed = False
        self.text = self.path.read_text(encoding="utf-8")
        self.lines = self.text.splitlines()
        self.type = None

    def fail(self, line, msg):
        self.failed = True
        print(f"{self.name}:{line}: FAIL {msg}")

    def warn(self, line, msg):
        print(f"{self.name}:{line}: warn {msg}")

    def check(self):
        self.front_matter()
        prose = self.classify()
        self.headings_and_lists(prose)
        self.words_and_images(prose)
        self.sentences(prose)
        self.counts(prose)

    def front_matter(self):
        fm = re.match(r"---\n(.*?)\n---\n", self.text, flags=re.S)
        if fm:
            m = re.search(r"^type:\s*(\S+)", fm.group(1), flags=re.M)
            self.type = m.group(1).strip() if m else None
        if self.args.no_front_matter:
            return
        if not fm:
            self.fail(1, "no front matter (--no-front-matter to allow)")
            return
        for key in self.args.front_matter_keys.split(","):
            if key and not re.search(rf"^{re.escape(key)}:", fm.group(1), flags=re.M):
                self.fail(1, f"front matter lacks {key}")

    def classify(self):
        """Return a list of (lineno, line, kind) for prose lines, with kind in prose/heading/table/callout."""
        out = []
        in_fm = False
        fence = None          # the fence string that opened a skipped block
        in_callout = 0
        callout_fence = []
        for i, line in enumerate(self.lines, 1):
            if i == 1 and line.strip() == "---":
                in_fm = True
                continue
            if in_fm:
                if line.strip() == "---":
                    in_fm = False
                continue
            if fence:
                if line.startswith(fence[:3]) and line.strip() == fence.strip():
                    fence = None
                continue
            d = DIRECTIVE.match(line)
            if d:
                mark, name = d.group(1), d.group(2).lower()
                if name in CALLOUT_DIRECTIVES:
                    in_callout += 1
                    callout_fence.append(mark)
                    out.append((i, line, "callout-open"))
                else:
                    fence = mark
                continue
            f = FENCE.match(line)
            if f:
                mark = f.group(1)
                if callout_fence and mark[:3] == callout_fence[-1][:3] and line.strip() == mark:
                    callout_fence.pop()
                    in_callout -= 1
                    continue
                fence = mark
                continue
            if line.startswith("%") or line.startswith("<!--"):
                continue
            if re.match(r"^\s*>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]", line, flags=re.I):
                out.append((i, line, "callout-open"))
                continue
            if line.startswith("|"):
                out.append((i, line, "table"))
                continue
            if line.startswith("#"):
                out.append((i, line, "heading"))
                continue
            kind = "callout" if in_callout else "prose"
            out.append((i, line.lstrip("> ") if line.startswith(">") and in_callout else line, kind))
        return out

    def headings_and_lists(self, prose):
        h2 = []
        list_count = 0
        list_start = 0
        for i, line, kind in prose:
            if kind == "heading":
                level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("# ").strip()
                if level > 5:
                    self.fail(i, "heading deeper than five levels")
                if level == 1 and len(title) > 65:
                    self.fail(i, f"title over 65 characters ({len(title)})")
                if level == 2:
                    h2.append((i, title))
                list_count = 0
                continue
            if kind != "prose" and kind != "callout":
                list_count = 0
                continue
            is_item = bool(LIST_ITEM.match(line)) and not line.startswith("  ") and not line.startswith("\t")
            is_sub = bool(LIST_ITEM.match(line)) and (line.startswith("  ") or line.startswith("\t"))
            if is_item:
                if list_count == 0:
                    list_start = i
                list_count += 1
                if list_count == 8:
                    self.fail(i, f"more than 7 items in the list starting at line {list_start}")
            elif line.strip() and not is_sub and not line.startswith("  ") and not line.startswith("\t"):
                list_count = 0
            if kind == "callout" and STEP_ITEM.match(line):
                self.fail(i, "a numbered step inside a callout")
        if self.type == "how-to":
            titles = [t for _, t in h2]
            includes = re.search(r"^(```+|~~~+|:::+)\s*\{include\}", self.text, flags=re.M)
            if includes and not titles:
                self.warn(1, "how-to headings come from an {include}: lint the included file")
            elif titles != HOWTO_HEADINGS:
                line = h2[0][0] if h2 else 1
                self.fail(line, "how-to headings must be exactly: " + " · ".join(HOWTO_HEADINGS)
                          + f" (found: {' · '.join(titles) or 'none'})")

    def words_and_images(self, prose):
        for i, line, kind in prose:
            if kind in ("table", "callout-open"):
                continue
            for m in IMAGE.finditer(line):
                alt = m.group(1).strip()
                if not alt:
                    self.fail(i, "image with no alt text")
                elif len(alt) > 150:
                    self.fail(i, f"alt text over 150 characters ({len(alt)})")
            if kind == "heading":
                continue
            plain = mentions_stripped(line)
            low = " " + plain.lower() + " "
            for w in BANNED:
                if re.search(r"(?<![a-z0-9-])" + re.escape(w) + r"(?![a-z0-9-])", low):
                    self.fail(i, f"banned word '{w}'")
            for w in WATCH:
                if re.search(r"(?<![a-z0-9-])" + w + r"(?![a-z0-9-])", low):
                    self.warn(i, f"watch word '{w}' (allowed when not about time)")
            for p in PHRASES:
                if p in plain:
                    self.fail(i, f"forbidden phrase '{p}'")

    def sentences(self, prose):
        para, start = [], 0

        def flush():
            if not para:
                return
            joined = " ".join(mentions_stripped(l).strip() for l in para)
            joined = re.sub(r"^\s*(\d+[.)]|[-*+])\s+", "", joined)
            sents = [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(“])", joined.strip()) if x.strip()]
            for x in sents:
                if words(x) > 25:
                    self.fail(start, f"sentence of {words(x)} words: {x[:60]}…")
            if len(sents) > 5 and not LIST_ITEM.match(para[0]):
                self.warn(start, f"paragraph of {len(sents)} sentences (3 to 5 wanted)")

        for i, line, kind in prose:
            if kind in ("heading", "table", "callout-open") or not line.strip():
                flush()
                para = []
                continue
            if LIST_ITEM.match(line):
                flush()
                para, start = [line], i
                continue
            if not para:
                start = i
            para.append(line)
        flush()

    def counts(self, prose):
        links = sum(len(LINK.findall(line)) for _, line, kind in prose if kind != "callout-open")
        if links > self.args.max_links:
            self.warn(1, f"{links} links on the page (at most {self.args.max_links})")
        callouts = sum(1 for _, _, kind in prose if kind == "callout-open")
        if callouts > 2:
            self.warn(1, f"{callouts} callouts on the page (at most 2)")
        body = [line for _, line, kind in prose if kind in ("prose", "callout") and line.strip()]
        link_only = body and all(LINK.search(l) or LIST_ITEM.match(l) for l in body)
        if link_only and self.type != "landing":
            self.warn(1, "a page that is only links (a landing page says type: landing)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--no-front-matter", action="store_true", help="do not require front matter")
    ap.add_argument("--front-matter-keys", default="type,owner,reader,review",
                    help="comma-separated keys every front matter must carry")
    ap.add_argument("--max-links", type=int, default=15)
    args = ap.parse_args(argv)
    rc = 0
    for path in args.files:
        page = Page(path, args)
        page.check()
        if page.failed:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
