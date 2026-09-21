#!/usr/bin/env python3
"""Check task references in text for the one defect that is locally decidable.

    refs.py --check                 # the board's own docs
    refs.py --check src/ README.md  # anywhere references are written

A reference written without its suffix is a defect. Two ways it goes wrong,
and neither needs another workspace to demonstrate:

  * It misresolves after a merge. `resolve_id` filters candidates by suffix
    only when the query has one, so a bare `0360` is the sole hit today and
    silently becomes the wrong hit once another branch's `0360.k3f` lands.
  * It is how a *predicted* id gets committed. `next_id` is highest + 1, so
    the next number is guessable; the suffix is not, because it comes from
    `secrets.choice`. A reference carrying a suffix is proof `new.py` ran.

What this deliberately does NOT fail on: a suffixed reference that doesn't
resolve in this checkout. That is the workflow the discriminator exists to
support - the task is real, it just lives on another branch or worktree.
Failing there would push people to "fix" a correct reference by hand, which
is how you get collisions back. It is reported under a separate heading,
never as an error, because from here it is indistinguishable from a typo'd
suffix and claiming otherwise would be a guess.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    all_ids, board_dir, find_root, load_config, parse_id,
)

# A reference is a kind word plus a number. Requiring the word is what keeps
# this out of the business of every other 4-digit number in a source file -
# years, ports, magic constants. Missing a reference written without its kind
# is the acceptable direction to be wrong in.
KIND_WORDS = ("task", "bug", "epic", "spike", "spec", "item")
_REF_RE = re.compile(
    r"\b(?P<kind>" + "|".join(KIND_WORDS) + r")s?\b[\s:=#]{1,3}"
    r"(?P<num>\d{1,6})(?:\.(?P<suffix>[a-z0-9]+))?\b",
    re.IGNORECASE,
)
# Frontmatter reference fields, where the kind word is the key itself.
_FIELD_RE = re.compile(
    r"^\s*-?\s*(?P<kind>epic|spec|depends_on|related|related_tasks)\s*:\s*"
    r"\[?\s*(?P<num>\d{1,6})(?:\.(?P<suffix>[a-z0-9]+))?",
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"}
TEXT_SUFFIXES = {
    ".md", ".py", ".txt", ".rst", ".yaml", ".yml", ".toml", ".json", ".cfg",
    ".ini", ".js", ".ts", ".tsx", ".jsx", ".sh", ".c", ".h", ".cpp", ".rs",
    ".go", ".java", ".rb", ".ipynb", ".tex", ".typ", ".sql", ".html", ".css",
}


class Ref:
    __slots__ = ("path", "lineno", "text", "kind", "number", "suffix", "line")

    def __init__(self, path, lineno, text, kind, number, suffix, line):
        self.path = path
        self.lineno = lineno
        self.text = text
        self.kind = kind
        self.number = number
        self.suffix = suffix
        self.line = line


def iter_files(paths: list[Path]):
    for p in paths:
        if p.is_file():
            yield p
        elif p.is_dir():
            for q in sorted(p.rglob("*")):
                if not q.is_file():
                    continue
                if any(part in SKIP_DIRS for part in q.parts):
                    continue
                if q.suffix.lower() in TEXT_SUFFIXES:
                    yield q


def scan_file(path: Path) -> list[Ref]:
    """Every reference-shaped mention in one file."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return []

    out = []
    for lineno, line in enumerate(lines, 1):
        # A document's own `id:` is not a reference to anything, and neither
        # is the generated index - it is rebuilt from the board, so a
        # complaint about it would be a complaint about index.py.
        if re.match(r"^\s*id\s*:", line):
            continue
        for m in _FIELD_RE.finditer(line):
            out.append(Ref(path, lineno, m.group(0).strip(), m.group("kind"),
                           int(m.group("num")), m.group("suffix") or "", line.strip()))
        for m in _REF_RE.finditer(line):
            out.append(Ref(path, lineno, m.group(0).strip(), m.group("kind").lower(),
                           int(m.group("num")), m.group("suffix") or "", line.strip()))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Check task references for missing suffixes.")
    p.add_argument("paths", nargs="*", type=Path,
                   help="files or directories to scan (default: the board's docs)")
    p.add_argument("--check", action="store_true",
                   help="exit nonzero if any suffix-less reference is found")
    p.add_argument("--root", type=Path, help="project root (default: auto-detect)")
    p.add_argument("--board", help="board root (default: $TASK_TRACKER_BOARD or 'docs')")
    args = p.parse_args()

    project_root = (args.root or find_root()).resolve()
    try:
        cfg = load_config(project_root, args.board)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not cfg.get("suffix_length", 3):
        # Nothing to require, so nothing to check. Say so rather than passing
        # silently: a green check here would imply a guarantee the board
        # cannot make without a discriminator.
        print("suffix_length is 0 on this board: predicted ids are "
              "undetectable and references cannot carry a suffix. "
              "Nothing to check.")
        return 0

    task_ids = all_ids(project_root, "tasks", args.board)
    spec_ids = all_ids(project_root, "specs", args.board)

    paths = args.paths or [
        board_dir(project_root, "tasks", args.board),
        board_dir(project_root, "specs", args.board),
    ]
    paths = [q for q in paths if q.exists()]
    if not paths:
        print("error: nothing to scan", file=sys.stderr)
        return 1

    index_name = "_index.md"
    missing, unresolved = [], []
    for f in iter_files(paths):
        if f.name == index_name:
            continue
        for ref in scan_file(f):
            ids = spec_ids if ref.kind == "spec" else task_ids
            local = [c for c in ids if parse_id(c)[0] == ref.number]

            if ref.suffix:
                if not any(parse_id(c)[1].startswith(ref.suffix) for c in local):
                    unresolved.append(ref)
                continue

            # Suffix-less. One exemption: it resolves to a legacy item whose
            # own id has no suffix, so there was never a suffix to write.
            if local and all(not parse_id(c)[1] for c in local):
                continue
            missing.append(ref)

    rel = lambda q: str(q.relative_to(project_root)) if q.is_relative_to(project_root) else str(q)  # noqa: E731

    if missing:
        print(f"suffix-less references ({len(missing)}) - these misresolve after a "
              f"merge, and are how a predicted id looks:")
        for r in missing:
            ids = spec_ids if r.kind == "spec" else task_ids
            hits = sorted(str(c) for c in ids if parse_id(c)[0] == r.number)
            target = f" -> currently resolves to {', '.join(hits)}" if hits else \
                     " -> no such item on this board"
            print(f"  {rel(r.path)}:{r.lineno}: {r.text}{target}")
            print(f"      {r.line}")
        print("fix: check which item you meant, then write the id with its "
              "suffix. If the item was never filed, file it with new.py - do "
              "not hand-assign the number you predicted, it may already be "
              "someone else's.")

    if unresolved:
        if missing:
            print()
        print(f"not on this board ({len(unresolved)}) - not errors: these may live "
              f"on another branch or worktree:")
        for r in unresolved:
            print(f"  {rel(r.path)}:{r.lineno}: {r.text}")

    if not missing and not unresolved:
        print("all references carry a suffix and resolve.")

    return 1 if (missing and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
