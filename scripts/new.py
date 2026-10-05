#!/usr/bin/env python3
"""Create a new spec or task with atomic ID allocation.

Usage:
    new.py spec  "Baseline experiment"
    new.py task  "Train baseline model" --spec 3 --tags training baseline
    new.py epic  "Reproduce paper X"
    new.py bug   "Loss NaN after epoch 5"  --epic 7
    new.py spike "Try alternative tokenizer" --tags exploratory
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    TASK_TYPES, all_ids, allocate_id, board_dir, board_lock, dump_frontmatter,
    find_root, load_config, NeedSlug, parse_frontmatter, resolve_id, slugify,
)

DIR_README = """\

## Evidence

This directory holds this task's intermediate evidence - logs, plots, scratch
analyses too bulky for the charter and not durable enough to exit yet. Resume
state is not here: it lives in `tasks/_handoffs/<id>.md`, gitignored and
shared by every task shape.

## Exits

Knowledge leaves this directory as it is produced, not at the end. Record each
destination in the `exits:` frontmatter field. A closed task whose artifacts
are all still inside its own directory was mis-filed.
"""


def _fail(exc) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return 1


def _resolve(value, ids, flag: str):
    """Turn a reference into a full id, or exit with the candidate list.

    Storing the resolved id rather than what was typed matters: `--epic 42` is
    unambiguous today and may not be after the next merge, and a reference
    already written as `0042.k3f` never goes ambiguous.
    """
    if value is None:
        return None
    try:
        return resolve_id(value, ids)
    except LookupError as exc:
        raise SystemExit(f"error: {flag}: {exc}")


def main() -> int:
    p = argparse.ArgumentParser(description="Create a new spec or task.")
    p.add_argument("kind", choices=["spec", *TASK_TYPES])
    p.add_argument("title")
    p.add_argument("--slug", help="the filename's readable half, in English; required "
                   "when the title is not English")
    p.add_argument("--description", help="one-line description")
    p.add_argument("--epic", help="parent epic id (tasks/bugs/spikes only); "
                                  "a bare number works while it is unambiguous")
    p.add_argument("--spec", help="related spec id (tasks/epics only)")
    p.add_argument("--tags", nargs="*", default=None)
    p.add_argument("--depends-on", nargs="*", default=None)
    p.add_argument("--priority", choices=["low", "medium", "high"])
    p.add_argument("--effort", choices=["S", "M", "L"])
    p.add_argument("--exits", nargs="*", default=None,
                   help="paths this task's knowledge will exit to")
    p.add_argument("--dir", dest="as_dir", action="store_true",
                   help="create NNNN-slug/README.md instead of NNNN-slug.md, "
                        "for a task that will grow live state and an evidence trail")
    p.add_argument("--root", type=Path, help="project root (default: auto-detect)")
    p.add_argument("--board", help="board root (default: $TASK_TRACKER_BOARD or 'docs'; "
                                   "empty puts the board at the project root)")
    args = p.parse_args()

    if args.as_dir and args.kind == "spec":
        print("error: --dir applies to tasks, not specs", file=sys.stderr)
        return 2

    try:
        slug = slugify(args.title, given=args.slug)
    except NeedSlug as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    project_root = (args.root or find_root()).resolve()
    skill_root = Path(__file__).resolve().parent.parent
    folder_name = "specs" if args.kind == "spec" else "tasks"
    folder = board_dir(project_root, folder_name, args.board)
    folder.mkdir(parents=True, exist_ok=True)

    tmpl_path = skill_root / "templates" / f"{args.kind}.md"
    if not tmpl_path.is_file():
        print(f"error: template not found: {tmpl_path}", file=sys.stderr)
        return 1
    tmpl_meta, tmpl_body = parse_frontmatter(tmpl_path.read_text())

    try:
        cfg = load_config(project_root, args.board)
    except ValueError as exc:
        return _fail(exc)

    with board_lock(project_root, args.board):
        # Resolve references before allocating, so a typo'd --spec fails
        # without burning an id.
        task_ids = all_ids(project_root, "tasks", args.board)
        spec_ids = all_ids(project_root, "specs", args.board)
        epic = _resolve(args.epic, task_ids, "--epic")
        spec = _resolve(args.spec, spec_ids, "--spec")
        deps = [_resolve(d, task_ids, "--depends-on") for d in (args.depends_on or [])]

        new_id = allocate_id(project_root, folder_name, cfg, args.board)
        today = date.today().isoformat()

        meta = dict(tmpl_meta)
        meta["id"] = new_id
        meta["title"] = args.title
        if args.kind == "spec":
            meta["status"] = "draft"
        else:
            meta["type"] = args.kind
            meta["status"] = "planned"
        meta["created"] = today
        meta["updated"] = today
        if args.description:
            meta["description"] = args.description
        if args.tags:
            meta["tags"] = args.tags
        if epic is not None:
            meta["epic"] = epic
        if spec is not None:
            meta["spec"] = spec
        if deps:
            meta["depends_on"] = deps
        if args.priority:
            meta["priority"] = args.priority
        if args.effort:
            meta["effort"] = args.effort
        if args.exits:
            meta["exits"] = args.exits

        stem = f"{new_id}-{slug}"
        body = tmpl_body
        if args.as_dir:
            task_dir = folder / stem
            if task_dir.exists():
                print(f"error: refusing to overwrite {task_dir}", file=sys.stderr)
                return 1
            task_dir.mkdir(parents=True)
            out_path = task_dir / "README.md"
            body = tmpl_body + DIR_README
        else:
            out_path = folder / f"{stem}.md"
        if out_path.exists():
            print(f"error: refusing to overwrite {out_path}", file=sys.stderr)
            return 1
        out_path.write_text(dump_frontmatter(meta, body))

    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
