#!/usr/bin/env python3
"""Move terminal-status items to archive/, append to monthly digests.

  archive.py                       # archive done/abandoned tasks AND specs
                                   # older than 14 days (default)
  archive.py --kind tasks
  archive.py --older-than-days 30
  archive.py --dry-run
  archive.py --prune-older-than-days 365   # delete archived files older than
                                           # a year, digests are always kept

Digests live at docs/{tasks,specs}/archive/digest-YYYY-MM.md and are appended
to (never rewritten from scratch), so prior digest entries survive --prune.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    as_date as _as_date, board_dir, display_id, handoff_path, iter_task_files,
    find_root, load_config, parse_frontmatter, parse_id,
)

TERMINAL = {"done", "abandoned", "archived"}


def _digest_append(digest: Path, ym: str, items: list[dict], dry: bool,
                   width: int = 4) -> None:
    if not digest.exists():
        header = f"# Archive digest {ym}\n\n"
    else:
        header = ""
    lines = []
    for m in items:
        idv = display_id(m["id"], width) if parse_id(m.get("id"))[0] is not None else "?"
        status = m.get("status", "?")
        title = m.get("title", "(no title)")
        lines.append(f"- {idv} [{status}] {title}")
    block = header + "\n".join(lines) + "\n"
    if dry:
        print(f"DIGEST {digest} (+{len(items)} entries)")
        return
    with open(digest, "a") as f:
        f.write(block)


def _archive_kind(root: Path, kind: str, cutoff: date, dry: bool,
                  board: str | None = None, width: int = 4) -> None:
    folder = board_dir(root, kind, board)
    if not folder.is_dir():
        return
    archive_root = folder / "archive"
    archive_root.mkdir(exist_ok=True)

    by_month: dict[str, list[dict]] = {}
    for p in iter_task_files(folder):
        try:
            meta, _ = parse_frontmatter(p.read_text())
        except Exception as exc:
            print(f"warning: skipping {p}: {exc}", file=sys.stderr)
            continue
        if meta.get("status") not in TERMINAL:
            continue
        when = _as_date(meta.get("updated")) or _as_date(meta.get("created"))
        if not when or when > cutoff:
            continue
        # A directory-shaped task archives as a whole directory: its evidence
        # trail is part of the record, not litter around the README.
        src = p.parent if p.name == "README.md" and p.parent != folder else p
        ym = when.strftime("%Y-%m")
        dest_dir = archive_root / ym
        dest_dir.mkdir(exist_ok=True)
        target = dest_dir / src.name
        if dry:
            print(f"DRY  {src.relative_to(root)} -> archive/{ym}/")
        else:
            shutil.move(str(src), str(target))
            print(f"MOVE {src.name} -> {kind}/archive/{ym}/")
        # The handoff is resume state for work that is now over. Deleting it
        # is safe by construction: gitignored, never cited, nothing durable in
        # it. Leaving it behind is how _handoffs/ stops being a reliable
        # answer to "what is mid-flight".
        if kind == "tasks":
            h = handoff_path(root, meta.get("id"), board)
            if h.is_file():
                if dry:
                    print(f"DRY  rm {h.relative_to(root)}")
                else:
                    h.unlink()
                    print(f"RM   {kind}/_handoffs/{h.name}")
        by_month.setdefault(ym, []).append(meta)

    for ym, items in by_month.items():
        _digest_append(archive_root / f"digest-{ym}.md", ym, items, dry, width)


def _prune_kind(root: Path, kind: str, cutoff: date, dry: bool,
                board: str | None = None) -> None:
    archive_root = board_dir(root, kind, board) / "archive"
    if not archive_root.is_dir():
        return
    for f in archive_root.rglob("*.md"):
        if f.name.startswith("digest-"):
            continue
        try:
            meta, _ = parse_frontmatter(f.read_text())
        except Exception:
            continue
        when = _as_date(meta.get("updated")) or _as_date(meta.get("created"))
        if not when or when > cutoff:
            continue
        if dry:
            print(f"DRY-PRUNE {f.relative_to(root)}")
        else:
            f.unlink()
            print(f"PRUNE {f.relative_to(root)}")


def main() -> int:
    p = argparse.ArgumentParser(description="Archive completed items and update digests.")
    p.add_argument("--kind", choices=["tasks", "specs", "all"], default="all")
    p.add_argument("--older-than-days", type=int, default=None,
                   help="default: archive_after_days from .task-tracker.md (14)")
    p.add_argument("--prune-older-than-days", type=int, default=None,
                   help="delete archived files older than N days (digests kept)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--root", type=Path)
    p.add_argument("--board", help="board root (default: $TASK_TRACKER_BOARD or 'docs')")
    args = p.parse_args()

    root = (args.root or find_root()).resolve()
    try:
        cfg = load_config(root, args.board)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    days = (args.older_than_days if args.older_than_days is not None
            else cfg["archive_after_days"])
    kinds = ["tasks", "specs"] if args.kind == "all" else [args.kind]
    cutoff = date.today() - timedelta(days=days)

    for kind in kinds:
        _archive_kind(root, kind, cutoff, args.dry_run, args.board, cfg["id_width"])

    if args.prune_older_than_days is not None:
        prune_cutoff = date.today() - timedelta(days=args.prune_older_than_days)
        for kind in kinds:
            _prune_kind(root, kind, prune_cutoff, args.dry_run, args.board)

    return 0


if __name__ == "__main__":
    sys.exit(main())
