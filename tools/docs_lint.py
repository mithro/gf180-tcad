#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Vendored (below this header) from github.com/mithro/dot-claude, branch
# docs-writing-skill, commit e0dde9e99ba4d0f9d01bdabc8ac51ef87603825b,
# marketplace/docs-writing/skills/writing-docs/scripts/docs_lint.py
# (sha256 d0dedd0829489311d2738420f3b670cfe7216010c28fde3b59f854488f5b79ff of the original file).
# Copyright Tim Ansell; Apache License 2.0 (the LICENSE at the root of that branch).
# Local additions: the block between "--- LOCAL" and "--- end LOCAL" and the lines marked
# "# LOCAL" (the --rules option: the house rules FIGURE, EQUATION and FILELINK of gf180-tcad
# spec §10.3). Everything else is the upstream file unchanged. Update by copying the new
# upstream file below this header, changing the commit and sha256, and carrying the LOCAL
# parts over.
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
        outside_sphinx = self.name in ("README.md", "CONTRIBUTING.md")  # LOCAL
        rules = getattr(self.args, "rules", ())  # LOCAL
        for line, check, msg in rule_findings(self.text, rules, not outside_sphinx):  # LOCAL
            self.failed = True  # LOCAL
            print(f"{self.path}:{line}: FAIL {check} {msg}")  # LOCAL
        if "figure" in rules:  # LOCAL
            for line, reason in figure_opt_outs(self.text):  # LOCAL
                print(f"{self.path}:{line}: NOTE FIGURE-OK {reason}")  # LOCAL

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


# --- LOCAL (gf180-tcad): the house rules of spec §10.3, owner 2026-11-03 02:00 ----------------
# Not part of the upstream file. Run only with --rules, so the upstream checks and their output
# are unchanged without it.

RULES = ("figure", "equation", "filelink")
OPT_OUT_WORDS = 6  # a figure-ok reason has six words or more
RULES_HELP = """\
house rules (--rules all, or a comma-separated subset of figure,equation,filelink):
  FIGURE    a section (the text from one heading to the next) whose prose names a physical
            situation (a word of SITUATION_NOUNS: curve, mesh, stack, profile, cross section,
            region, band, band diagram, gate, oxide, channel, doping, depletion, fringe, plan
            view, drawing, plot, geometry and others, or a plural; "the well", "n-well",
            "electric field") or "the figure above" has no {figure} directive and no {numref}
            role. Tables, headings, code, comments, glossary bodies and role targets are not
            prose; a {term} role's text is; a software stack is not a stack. In README.md and
            CONTRIBUTING.md (read on GitHub) a Markdown image counts as a figure. Opt-out for a
            section whose noun is not a physical thing (a mesh file, a sweep command):
            <!-- figure-ok: a reason of six words or more --> in the section. Each opt-out
            prints PATH:LINE: NOTE FIGURE-OK reason.
  FIGURE-FORM  a {figure} with no :name:, no caption, or no {numref} on the page citing it.
            The only-dark twin of a light/dark pair is exempt (the light twin carries the name).
            A {numref} to a target not on the page needs the page's title in its text
            ({numref}`Figure %s of <title> <name>`): numbers restart on each page.
  EQUATION  a display math block that is not in the house form: $$ ... $$ (label), then a line
            "where", then a list with one item per symbol, each starting with the symbol in
            $...$ and ending with ", in <SI unit symbols>" (F/m², cm⁻³) or ", dimensionless".
            The symbols are parsed from the LaTeX (a letter or Greek letter with its
            subscript); every one must be defined, and no item may define a symbol the equation
            does not use. A {math} directive is reported too.
  FILELINK  a file or path that is not a link: inline code that is a path (under results/,
            tools/, data/, docs/, src/, tests/, docker/, third_party/, bin/ or logs/), a
            file name with an extension (.py, .json, .toml, .md, .csv and similar, with an
            optional :line suffix) or Makefile, Dockerfile, README and similar. In bare prose:
            repository paths, file names with an extension, Makefile, Dockerfile and
            Containerfile. A role ({repo}, {test}) or [text](url) is a link. Code blocks
            are skipped; figure captions and tables are checked; `np.log` is code, not a file.
            A path under ~/ is on the reader's own computer, with nothing to link: not reported.
Each finding prints PATH:LINE: FAIL CHECK message.
"""

SITUATION_NOUNS = ("curve", "mesh", "stack", "profile", "cross section", "region", "sweep",
                   "layout", "die", "junction", "band", "band diagram", "band gap", "bandgap",
                   "gate", "oxide", "channel", "body", "bodies", "doping", "dopant", "depletion",
                   "depleted layer", "fringe", "plan view", "drawing", "diagram", "plot", "graph",
                   "crystal", "bond")
# Not "geometry": in these docs it names a W/L size ({term}`geometry id`), not a shape.
# A space in a noun matches a space or a hyphen ("cross-section", "plan-view"). Longer nouns
# first, so "band diagram" wins over "band".
_NOUN = re.compile(r"(?<![\w-])(" + "|".join(
    re.escape(n).replace(r"\ ", r"[\s-]+") for n in sorted(SITUATION_NOUNS, key=len, reverse=True))
    + r")(e?s)?(?![\w-])", flags=re.I)
# Nouns with a common non-physical sense count only with a qualifier: "the well" or "n-well",
# not "works well"; "electric field", not "the field `t_ox`".
_QUALIFIED_NOUN = re.compile(
    r"(?:\b[np][-+]?-|\bdeep\s+|\bthe\s+|\beach\s+|\bone\s+|\ba\s+)(wells?)(?![\w-])|\b(wells)\b"
    r"|\b(?:electric|fringe|fringing|lateral|vertical|surface)\s+(fields?)\b", flags=re.I)
_ABOVE = re.compile(r"\b((?:figure|drawing|plot|graph|diagram|picture|image)s?\s+(?:above|below))\b",
                    flags=re.I)
_FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,}|:{3,})\s*(.*)$")
_PROSE_DIRECTIVES = CALLOUT_DIRECTIVES | {"dropdown", "card", "tab-item", "tab-set"}
_MATH_OPEN = re.compile(r"^\s*\$\$(.*)$")
_MATH_CLOSE = re.compile(r"^(.*?)\$\$\s*(?:\((?P<label>[\w.:-]+)\))?\s*$")
_ROLE = re.compile(r"\{(?P<name>[\w:.-]+)\}`(?P<body>[^`]*)`")
_MD_LINK = re.compile(r"\[(?:[^\[\]]|\[[^\]]*\])*\]\([^)]*\)")
_CODE = re.compile(r"(?<!`)`(?P<body>[^`]+)`(?!`)")
_PATH_DIRS = r"(results|tools|data|docs|src|tests|docker|third_party|bin|logs)"
_PATH_EXTS = r"(py|json|toml|md|csv|tsv|yml|yaml|txt|svg|png|sh|cfg|ini|lock|gds|tcl|ipynb|log|pdf|msh|exo)"
_PLAIN_NAMES = r"(Makefile|Dockerfile|Containerfile|README|LICENSE|CONTRIBUTING|CHANGELOG)"
_LINE_NO = r"(:\d+(-\d+)?)"
_PATHLIKE = re.compile(rf"^(\./)?{_PATH_DIRS}/\S*$"
                       rf"|^[^\s/]*(/[^\s/]+)*\.{_PATH_EXTS}(#\S*|::\S*|{_LINE_NO})?$"
                       rf"|^([^\s/]+/)*{_PLAIN_NAMES}{_LINE_NO}?$")
# A file name in prose, outside code, roles and links: a path under a repository folder, a path
# under ~/, or a name with a file extension.
_PROSE_PATH = re.compile(rf"(?<![\w/.~-])((\./)?{_PATH_DIRS}/[\w./-]*[\w/]"
                         rf"|([\w.-]+/)*(Makefile|Dockerfile|Containerfile)"
                         rf"|[\w-]+(/[\w.-]+)*\.{_PATH_EXTS}{_LINE_NO}?)(?![\w/-])")
# A path under ~/ is a file on the reader's own computer: there is nothing to link to, so
# FILELINK does not report it (link the code that writes it where the text needs one).
# `np.log`, `logger.log`, `self.md`: Python names, not files.
_CODE_NAMES = {"np", "numpy", "math", "logger", "logging", "log", "self", "cls", "os", "sys", "re",
               "sp", "scipy", "plt", "pd", "json"}
GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta",
         "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "varrho", "sigma",
         "varsigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta",
         "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega"}
# Upright function names: "sin x" written without the backslash is sin, not s, i and n.
_FUNCTION_NAMES = {"sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh", "coth",
                   "arcsin", "arccos", "arctan", "exp", "ln", "log", "lg", "max", "min", "sup",
                   "inf", "lim", "det", "erf", "erfc", "sgn", "arg"}
_TEXT_COMMANDS = {"mathrm", "text", "textrm", "operatorname", "mbox", "hbox", "label", "tag"}
_WHERE_ITEM = re.compile(r"^\s*[-*]\s+(?P<syms>\$[^$]+\$(?:\s*(?:,|and)\s*\$[^$]+\$)*)(?P<rest>.*)$",
                         flags=re.S)
_UNIT = re.compile(r",\s*(in\s+(?P<unit>[^,;]+?)|dimensionless)[.;]?\s*$", flags=re.S)
# An SI unit written with symbols: m, cm⁻³, F/m², m²/(V·s), eV, cm^-3, 1/cm³.
_UNIT_ONE = (r"(?:(?:[YZEPTGMkhdcmµμunpfa]?(?:mol|cd|Hz|Pa|eV|rad|sr|Wb|Ω|m|s|g|A|K|V|F|C|J|W|S|H|T|N|L))"
             r"|1)(?:\^\{?[-−]?\d+\}?|[⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)?")
_UNIT_EXPR = re.compile(rf"{_UNIT_ONE}(?:\s*[·⋅*/ ]\s*{_UNIT_ONE})*")


def _is_unit(m):
    """True when a 'where' item ends with ', dimensionless' or ', in <SI unit symbols>'."""
    if not m:
        return False
    unit = m.group("unit")
    return unit is None or bool(_UNIT_EXPR.fullmatch(re.sub(r"[()]", "", unit.strip())))


def _group(s, i):
    """The content of the brace group that opens at s[i] == "{", and the index after it."""
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _subscript(s):
    s = re.sub(r"\\(" + "|".join(_TEXT_COMMANDS) + r")\s*\{([^{}]*)\}", r"\2", s)
    return re.sub(r"\\[,;:! ]|[\s{}]", "", s)


def latex_symbols(latex):
    """The symbols of a LaTeX formula: each Latin letter or Greek letter with its subscript, as
    'V_bi' or '\\varepsilon_si' (braces, spaces and \\mathrm dropped from the subscript)."""
    out, i = set(), 0
    while i < len(latex):
        c = latex[i]
        base = None
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+)", latex[i:])
            if not m:
                i += 2
                continue
            name, i = m.group(1), i + len(m.group(0))
            if name in _TEXT_COMMANDS:
                while i < len(latex) and latex[i] == " ":
                    i += 1
                if i < len(latex) and latex[i] == "{":
                    _, i = _group(latex, i)
                continue
            if name not in GREEK:
                continue
            base = "\\" + name
        elif c.isalpha() and c.isascii():
            word = re.match(r"[A-Za-z]+", latex[i:]).group(0)
            if word in _FUNCTION_NAMES and (i == 0 or not latex[i - 1].isalpha()):
                i += len(word)  # an upright function name written without its backslash
                continue
            base, i = c, i + 1
        else:
            i += 1
            continue
        if i < len(latex) and latex[i] == "_":
            i += 1
            if i < len(latex) and latex[i] == "{":
                sub, i = _group(latex, i)
            elif i < len(latex) and latex[i] == "\\":
                m = re.match(r"\\[A-Za-z]+", latex[i:])
                sub = m.group(0) if m else latex[i:i + 2]
                i += len(sub)
            else:
                sub, i = latex[i:i + 1], i + 1
            base += "_" + _subscript(sub)
        while i < len(latex) and latex[i] == "'":
            base, i = base + "'", i + 1
        out.add(base)
    return out


def _rule_lines(text):
    """(lineno, line, kind) for each line; kind is prose, table, heading, caption, figure, math,
    mathdir, code, option, comment, label, blank or front."""
    lines = text.splitlines()
    out, stack, in_comment, in_math = [], [], False, False
    front = 0
    if lines and lines[0].strip() == "---":
        front = next((k + 1 for k in range(1, len(lines)) if lines[k].strip() == "---"), 0)
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if i <= front:
            out.append((i, line, "front"))
            continue
        if stack:
            mark, kind = stack[-1]
            if s and set(s) == {mark[0]} and len(s) >= len(mark):
                stack.pop()
                out.append((i, line, "fence"))
                continue
            if kind in ("code", "mathdir"):
                out.append((i, line, "code"))
                continue
            if kind == "figure" and re.match(r"^\s*:[\w-]+:", line):
                out.append((i, line, "option"))
                continue
        if in_comment:
            out.append((i, line, "comment"))
            in_comment = "-->" not in line
            continue
        if in_math:
            out.append((i, line, "math"))
            in_math = not _MATH_CLOSE.match(line)
            continue
        f = _FENCE_OPEN.match(line)
        if f and f.group(2)[0] in "`~:":
            info = f.group(3).strip()
            d = re.match(r"^\{([\w:-]+)\}", info)
            name = d.group(1).lower() if d else None
            if name == "figure":
                kind = "figure"
            elif name == "math":
                kind = "mathdir"
            elif name in _PROSE_DIRECTIVES:
                kind = "callout"
            else:
                kind = "code"
            stack.append((f.group(2), kind))
            out.append((i, line, kind if kind in ("figure", "mathdir") else "fence"))
            continue
        context = stack[-1][1] if stack else None
        if s.startswith("<!--"):
            out.append((i, line, "comment"))
            in_comment = "-->" not in line
            continue
        m = _MATH_OPEN.match(line)
        if m:
            out.append((i, line, "math"))
            rest = m.group(1)
            in_math = not (rest.strip() and _MATH_CLOSE.match(rest))
            continue
        if not s:
            kind = "blank"
        elif context == "figure":
            kind = "caption"
        elif re.match(r"^\([\w.:-]+\)=\s*$", s) or s.startswith("%"):
            kind = "label"
        elif s.startswith("|"):
            kind = "table"
        elif re.match(r"^#{1,6}\s", s) and context is None:
            kind = "heading"
        elif context == "callout" and re.match(r"^:[\w-]+:", s):
            kind = "option"
        else:
            kind = "prose"
        out.append((i, line, kind))
    return out


def _visible(line):
    """Prose as a reader sees it: a {term} role keeps its text, other roles, code, math and link
    targets go."""
    line = re.sub(r"\{term\}`([^`<]*?)\s*(<[^`>]*>)?`", r"\1", line)
    line = _ROLE.sub(" ", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
    line = re.sub(r"`[^`]*`|\$[^$]*\$|\{\{[^}]*\}\}|<!--.*?-->", " ", line)
    return line


_SOFTWARE_STACK = re.compile(r"\b(software|TCAD|tool|image|latest|stable|dev|2023|Sept-2023|two|both)"
                             r"\s+stacks?\b|\bstacks?\s+of\s+20\d\d\b|\bstacks?\s+of\s+(?:the\s+)?(?:\w+\s+)?results\b"
                             r"|\b(?:entry|quality|review|merge)\s+gates?\b",
                             flags=re.I)
_FIGURE_OK = re.compile(r"<!--\s*figure-ok:\s*(?P<reason>[^>]*?)\s*-->")
_IMAGE_LINE = re.compile(r"^\s*!\[[^\]]+\]\([^)]+\)")


def figure_findings(lines, sphinx=True):
    out, sections = [], [[]]
    for row in lines:
        if row[2] == "heading":
            sections.append([])
        sections[-1].append(row)
    for sec in sections:
        has_figure = any(k == "figure" or "{numref}" in ln for _, ln, k in sec)
        if not sphinx:
            has_figure = has_figure or any(_IMAGE_LINE.match(ln) for _, ln, _k in sec)
        opt_out = any(len((m.group("reason") or "").split()) >= OPT_OUT_WORDS
                      for _, ln, _k in sec for m in _FIGURE_OK.finditer(ln))
        if has_figure or opt_out:
            continue
        title = sec[0][1].lstrip("# ").strip() if sec and sec[0][2] == "heading" else "(page top)"
        for i, line, kind in sec:
            if kind != "prose":
                continue
            text = _SOFTWARE_STACK.sub(" ", _visible(line))
            above = _ABOVE.search(text)
            if above:
                out.append((i, "FIGURE", f"section '{title}' refers to the {above.group(1).lower()} "
                                         "with no {numref}: cite the figure by its name"))
                break
            m = _NOUN.search(text) or _QUALIFIED_NOUN.search(text)
            if m:
                noun = next(g for g in m.groups() if g and g.lower() not in ("s", "es"))
                out.append((i, "FIGURE", f"section '{title}' describes a {noun.lower()} with no "
                                         "{figure} and no {numref} in it"))
                break
    return out


def figure_opt_outs(text):
    """(line, reason) of each <!-- figure-ok: reason --> whose reason has OPT_OUT_WORDS words or
    more; --rules prints each as a NOTE, and the baseline counts them as FIGURE-OK."""
    out = []
    for i, line, kind in _rule_lines(text):
        if kind != "comment":
            continue
        for m in _FIGURE_OK.finditer(line):
            reason = " ".join((m.group("reason") or "").split())
            if len(reason.split()) >= OPT_OUT_WORDS:
                out.append((i, reason))
    return out


def _figure_blocks(lines):
    """(line, options, caption lines) of each {figure} directive."""
    out, k, n = [], 0, len(lines)
    while k < n:
        i, line, kind = lines[k]
        k += 1
        if kind != "figure":
            continue
        opts, caption = {}, []
        while k < n and lines[k][2] in ("option", "caption", "blank"):
            _, ln, kd = lines[k]
            if kd == "option":
                o = re.match(r"^\s*:([\w-]+):\s*(.*)$", ln)
                opts[o.group(1)] = o.group(2).strip()
            elif kd == "caption":
                caption.append(ln.strip())
            k += 1
        out.append((i, opts, caption))
    return out


def figure_form_findings(lines):
    """FIGURE-FORM: a {figure} needs a :name:, a caption and a {numref} on the page that cites
    it. The dark twin of a light/dark pair (:figclass: only-dark) carries no name and is exempt."""
    cited, refs = set(), []
    for i, line, kind in lines:
        if kind in ("prose", "table", "caption", "heading"):
            for m in re.finditer(r"\{numref\}`(?:([^`<]*)<)?\s*([^`<>]+?)\s*>?`", line):
                cited.add(m.group(2))
                refs.append((i, m.group(1), m.group(2)))
    out = []
    # Numbers restart on each page: a {numref} to another page's figure names the page.
    targets = {opts["name"] for _, opts, _ in _figure_blocks(lines) if opts.get("name")}
    targets |= {re.match(r"^\s*\(([\w.:-]+)\)=", ln).group(1) for _, ln, k in lines if k == "label"
                and re.match(r"^\s*\(([\w.:-]+)\)=", ln)}
    for i, text, target in refs:
        if target in targets:
            continue
        words = re.sub(r"%s|\{number\}|\{name\}|\bFig(ure)?\b\.?", " ", text or "").split()
        if len(words) < 2:
            out.append((i, "FIGURE-FORM", f"{{numref}} to '{target}', a figure on another page: "
                                          "numbers restart on each page, so write the page's "
                                          f"title in the text, {{numref}}`Figure %s of <title> "
                                          f"<{target}>`"))
    for i, opts, caption in _figure_blocks(lines):
        if "only-dark" in opts.get("figclass", "").split():
            continue
        name = opts.get("name")
        if not name:
            out.append((i, "FIGURE-FORM", "this {figure} has no :name:, so the text cannot cite it "
                                          "with {numref}: name it (the light twin of a pair)"))
        elif not any(caption):
            out.append((i, "FIGURE-FORM", f"the {{figure}} '{name}' has no caption: write one"))
        elif name not in cited:
            out.append((i, "FIGURE-FORM", f"no {{numref}} on the page cites the {{figure}} '{name}': "
                                          "cite it in the text"))
    return out


def _where_list(lines, j):
    """The items (start line, text) of the "where" list that starts at index j, or None."""
    n = len(lines)
    while j < n and lines[j][2] == "blank":
        j += 1
    if j >= n or not re.match(r"^\s*where:?\s*$", lines[j][1], flags=re.I):
        return None
    j += 1
    while j < n and lines[j][2] == "blank":
        j += 1
    items = []
    while j < n:
        i, line, kind = lines[j]
        if re.match(r"^\s*[-*]\s+", line) and kind == "prose":
            items.append([i, line.strip()])
        elif items and kind == "prose" and line.startswith((" ", "\t")):
            items[-1][1] += " " + line.strip()
        else:
            break
        j += 1
    return items


def equation_findings(lines):
    out, j, n = [], 0, len(lines)
    while j < n:
        i, line, kind = lines[j]
        if kind == "mathdir":
            out.append((i, "EQUATION", "a {math} directive: the house form is $$ ... $$ (label) "
                                       "with a 'where' list"))
            j += 1
            continue
        if kind != "math":
            j += 1
            continue
        start, body = i, []
        while j < n and lines[j][2] == "math":
            body.append(lines[j][1])
            j += 1
        block = "\n".join(body)
        close = _MATH_CLOSE.match(body[-1].strip()) if body else None
        label = close.group("label") if close else None
        latex = re.sub(r"\$\$\s*(\([\w.:-]+\))?", " ", block)
        symbols = latex_symbols(latex)
        if not label:
            out.append((start, "EQUATION", "display math with no label: end it with $$ (eq-name) "
                                           "and cite it with {math:numref}"))
        items = _where_list(lines, j)
        if items is None:
            out.append((start, "EQUATION", "no 'where' list after the equation defines "
                                           + ", ".join(sorted(symbols))))
            continue
        defined = set()
        # One item may hold several definitions: "$E$ is ..., in J; $m$ is ..., in kg."
        defs = [(n, part if k == 0 else "- " + part)
                for n, it in items for k, part in enumerate(re.split(r";\s+(?=\$)", it))]
        for line_no, item in defs:
            m = _WHERE_ITEM.match(item)
            if not m:
                out.append((line_no, "EQUATION", "a 'where' item that does not start with its "
                                                 "symbol in $...$"))
                continue
            item_syms = set()
            for span in re.findall(r"\$([^$]+)\$", m.group("syms")):
                item_syms |= latex_symbols(span)
            defined |= item_syms
            extra = item_syms - symbols
            if extra:
                out.append((line_no, "EQUATION", "the 'where' list defines " + ", ".join(sorted(extra))
                                                 + ", which the equation does not use"))
            if not _is_unit(_UNIT.search(m.group("rest"))):
                out.append((line_no, "EQUATION", f"the 'where' item for {m.group('syms')} gives no "
                                                 "unit: end it with ', in <SI unit symbol>' (F/m², "
                                                 "cm⁻³) or ', dimensionless'"))
        missing = symbols - defined
        if missing:
            out.append((start, "EQUATION", "the 'where' list does not define "
                                           + ", ".join(sorted(missing))))
    return out


def filelink_findings(lines):
    out, open_code = [], False
    for i, line, kind in lines:
        if kind not in ("prose", "table", "heading", "caption"):
            open_code = False
            continue
        # A code span that a line break splits: the text up to its closing backtick is code.
        bare = line
        if open_code:
            bare = " " + line.split("`", 1)[1] if "`" in line else ""
        open_code = (open_code and "`" not in line) or bool(bare.count("`") % 2)
        if bare.count("`") % 2:
            bare = bare[: bare.rindex("`")]
        linked = [m.span() for m in _ROLE.finditer(line)] + [m.span() for m in _MD_LINK.finditer(line)]
        for m in _CODE.finditer(line):
            body = m.group("body").strip()
            if ("://" in body or body.startswith("~/") or not _PATHLIKE.match(body)
                    or _is_code_name(body)):
                continue
            if any(a <= m.start() < b for a, b in linked):
                continue
            out.append((i, "FILELINK", f"`{body}` is not a link: link the file "
                                       "({repo} for a file of this repository, a GitHub URL at a "
                                       "pinned commit otherwise)"))
        for m in _PROSE_PATH.finditer(_bare_prose(bare)):
            body = m.group(1)
            if _is_code_name(body):
                continue
            out.append((i, "FILELINK", f"`{body}` (in the prose) is not a link: link the file "
                                       "({repo} for a file of this repository, a GitHub URL at a "
                                       "pinned commit otherwise)"))
    return out


def _is_code_name(body):
    """`np.log`, `logger.log`, `self.md`: a Python name and an attribute, not a file."""
    m = re.fullmatch(r"([A-Za-z_]\w*)\.(\w+)", body)
    return bool(m) and m.group(1) in _CODE_NAMES


def _bare_prose(line):
    """The text of a line outside code, roles, links (their text too), math, URLs and comments,
    each replaced by a space: where a file name is not a link."""
    line = re.sub(r"<!--.*?-->", " ", line)
    line = _ROLE.sub(" ", line)
    line = _MD_LINK.sub(" ", line)
    line = re.sub(r"`[^`]*`|\$[^$]*\$|\{\{[^}]*\}\}|<[^>]*>|https?://\S+", " ", line)
    return line


def rule_findings(text, rules=RULES, sphinx=True):
    """(line, CHECK, message) of each finding of the house rules in a page's text. With
    sphinx=False (README.md, CONTRIBUTING.md: read on GitHub) a Markdown image is a figure."""
    lines = _rule_lines(text)
    out = []
    if "figure" in rules:
        out += figure_findings(lines, sphinx)
        out += figure_form_findings(lines)
    if "equation" in rules:
        out += equation_findings(lines)
    if "filelink" in rules:
        out += filelink_findings(lines)
    return sorted(out)

# --- end LOCAL ------------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=RULES_HELP)  # LOCAL: epilog
    ap.add_argument("files", nargs="+")
    ap.add_argument("--no-front-matter", action="store_true", help="do not require front matter")
    ap.add_argument("--front-matter-keys", default="type,owner,reader,review",
                    help="comma-separated keys every front matter must carry")
    ap.add_argument("--max-links", type=int, default=15)
    ap.add_argument("--rules", default="", metavar="all|figure,equation,filelink",  # LOCAL
                    help="also check the house rules FIGURE, EQUATION and FILELINK (see below)")  # LOCAL
    args = ap.parse_args(argv)
    args.rules = RULES if args.rules == "all" else tuple(r for r in args.rules.split(",") if r)  # LOCAL
    unknown = set(args.rules) - set(RULES)  # LOCAL
    if unknown:  # LOCAL
        ap.error(f"unknown rule(s): {', '.join(sorted(unknown))}")  # LOCAL
    rc = 0
    for path in args.files:
        page = Page(path, args)
        page.check()
        if page.failed:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
