#!/usr/bin/env python3
"""Promote a file-shaped task to a directory, links included.

    promote.py 42             # tasks/0042.k3f-slug.md -> tasks/0042.k3f-slug/README.md
    promote.py 42.k3f --dry-run

The shape of a task is not knowable when it is filed. You find out it needs a
directory the moment it grows an evidence trail, which is always later. So the
two shapes are a transition, not a choice, and this is the transition.

The move itself is one `git mv`. What makes it worth a script is the link
churn, which is silent when done by hand:

  * The charter drops one level, so every relative link inside it shifts:
    `../adr/x.md` -> `../../adr/x.md`, a sibling task `0012.k3f-y.md` ->
    `../0012.k3f-y.md`.
  * Every inbound link elsewhere on the board now needs `/README.md`.

Neither breaks loudly. A markdown link to a moved file renders fine and just
goes nowhere, so a promotion done by hand leaves rot that surfaces months
later, in whichever reader followed the link.

Resume state is NOT affected: it lives in `tasks/_handoffs/<id>.md` for both
shapes. Needing a handoff is not a reason to promote - only evidence is.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    board_dir, board_lock, board_root, find_root, iter_task_files,
    parse_frontmatter, parse_id, resolve_id,
)

# Inline links `](target)` and reference definitions `[id]: target`. Deliberate
# omissions: autolinks and bare URLs, neither of which can be a relative path.
_INLINE_RE = re.compile(r"(?<=\]\()(?P<t>[^)\s]+)(?=[)\s])")
_REFDEF_RE = re.compile(r"(?m)^(?P<pre>\[[^\]]+\]:\s+)(?P<t>\S+)")

# A target nothing should touch: absolute, a scheme, a bare fragment, or a
# mail/protocol form. Everything else is relative to the file it sits in, and
# therefore shifts when the file does.
_ABSOLUTE_RE = re.compile(r"^(?:[a-zA-Z][\w+.-]*:|//|/|#)")


def _shift(target: str) -> str:
    """One level deeper: the charter moved from `tasks/X.md` to `tasks/X/`."""
    if _ABSOLUTE_RE.match(target):
        return target
    if target.startswith("./"):
        target = target[2:]
    return "../" + target


def _rewrite_outbound(text: str) -> tuple[str, int]:
    n = 0

    def sub_inline(m):
        nonlocal n
        new = _shift(m.group("t"))
        n += new != m.group("t")
        return new

    def sub_refdef(m):
        nonlocal n
        new = _shift(m.group("t"))
        n += new != m.group("t")
        return m.group("pre") + new

    text = _INLINE_RE.sub(sub_inline, text)
    text = _REFDEF_RE.sub(sub_refdef, text)
    return text, n


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
TEXT_SUFFIXES = {".md", ".py", ".txt", ".rst", ".yaml", ".yml", ".toml",
                 ".json", ".ipynb", ".tex", ".typ", ".html"}


def _scan_paths(paths):
    for p in paths:
        if p.is_file():
            yield p
        elif p.is_dir():
            for q in sorted(p.rglob("*")):
                if not q.is_file() or any(s in SKIP_DIRS for s in q.parts):
                    continue
                if q.suffix.lower() in TEXT_SUFFIXES:
                    yield q


def _git_mv(src: Path, dest: Path, root: Path) -> bool:
    """git mv when the board is tracked, so the rename survives as a rename.

    Falls back to a plain rename rather than failing: a board does not have to
    be in git, and the promotion is still correct without it.
    """
    try:
        r = subprocess.run(["git", "-C", str(root), "mv", str(src), str(dest)],
                           capture_output=True, text=True)
        return r.returncode == 0
    except OSError:
        return False


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convert a file-shaped task into a directory-shaped one.")
    p.add_argument("id", help="task id; a bare number works while unambiguous")
    p.add_argument("--dry-run", action="store_true",
                   help="report the move and every link that would change")
    p.add_argument("--also", nargs="*", type=Path, default=None,
                   help="extra paths to scan for inbound links (default: the "
                        "whole board)")
    p.add_argument("--root", type=Path, help="project root (default: auto-detect)")
    p.add_argument("--board", help="board root (default: $TASK_TRACKER_BOARD or 'docs')")
    args = p.parse_args()

    root = (args.root or find_root()).resolve()
    folder = board_dir(root, "tasks", args.board)
    if not folder.is_dir():
        print(f"error: no task board at {folder}", file=sys.stderr)
        return 1

    with board_lock(root, args.board):
        by_id = {}
        for path in iter_task_files(folder):
            try:
                meta, _ = parse_frontmatter(path.read_text())
            except Exception as exc:
                print(f"warning: skipping {path}: {exc}", file=sys.stderr)
                continue
            if parse_id(meta.get("id"))[0] is not None:
                by_id[str(meta["id"])] = path

        try:
            full_id = resolve_id(args.id, by_id)
        except LookupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        src = by_id[full_id]
        if src.name == "README.md":
            print(f"error: {full_id} is already directory-shaped: "
                  f"{src.parent}", file=sys.stderr)
            return 1

        task_dir = src.with_suffix("")
        dest = task_dir / "README.md"
        if task_dir.exists():
            print(f"error: refusing to overwrite {task_dir}", file=sys.stderr)
            return 1

        # Outbound first, on the file still in place: if anything below fails,
        # nothing has moved and nothing was rewritten.
        old_text = src.read_text()
        new_text, out_n = _rewrite_outbound(old_text)

        # Inbound: the old filename is a unique enough token that a plain
        # substring swap is safe, and it works regardless of how deep the
        # linking file sits or what prefix it wrote.
        old_name, new_name = src.name, f"{task_dir.name}/README.md"
        scan = args.also if args.also else [board_root(root, args.board)]
        inbound = []
        for f in _scan_paths([q for q in scan if q.exists()]):
            if f == src:
                continue
            try:
                text = f.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if old_name in text:
                inbound.append((f, text.count(old_name),
                                text.replace(old_name, new_name)))

        rel = lambda q: str(q.relative_to(root)) if q.is_relative_to(root) else str(q)  # noqa: E731

        if args.dry_run:
            print(f"DRY  {rel(src)} -> {rel(dest)}")
            print(f"DRY  {out_n} outbound link(s) shifted one level")
            for f, count, _ in inbound:
                print(f"DRY  {rel(f)}: {count} inbound link(s) -> {new_name}")
        else:
            task_dir.mkdir()
            if not _git_mv(src, dest, root):
                src.rename(dest)
            dest.write_text(new_text)
            for f, _count, text in inbound:
                f.write_text(text)
            print(rel(dest))
            print(f"  {out_n} outbound link(s) shifted, "
                  f"{sum(c for _, c, _ in inbound)} inbound link(s) retargeted "
                  f"across {len(inbound)} file(s)")

        # exits: entries are paths, but nothing pins down what they are
        # relative to, so shifting them would be a guess. Say so instead of
        # guessing wrong in silence.
        meta, _ = parse_frontmatter(old_text)
        relative_exits = [e for e in (meta.get("exits") or [])
                          if isinstance(e, str) and not _ABSOLUTE_RE.match(e)]
        if relative_exits:
            print(f"note: check these relative `exits:` entries by hand - "
                  f"they may have shifted a level too: "
                  f"{', '.join(relative_exits)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
