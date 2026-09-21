#!/usr/bin/env python3
"""Find (and optionally claim) the next available task.

Eligibility: status == planned, all depends_on resolved to done/abandoned,
plus any --epic/--spec/--tag/--type filters.

Ranking: priority (high < medium < low), then most-recently-updated first,
then id. Unset fields sort *after* every explicit value, so annotating one
task never demotes it below the tasks nobody has annotated. Effort joins the
key only behind --prefer-small, for the same reason.

With --claim, the transition planned -> in-progress is performed under a
board-wide flock so two agents can't grab the same task.
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager, nullcontext
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    as_date, board_dir, board_lock, display_id, dump_frontmatter, find_root,
    handoff_path, id_sort_key, iter_docs, iter_task_files, load_config,
    parse_frontmatter, parse_id, resolve_id,
)

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
EFFORT_RANK = {"S": 0, "M": 1, "L": 2}
# Unset sorts after every explicit value. Defaulting it to the middle of the
# scale made an unannotated board tie on every component, so "next" collapsed
# to "lowest id" - permanently, since nothing ever breaks the tie.
UNSET = 99


def _rank(meta: dict, prefer_small: bool = False) -> tuple:
    key: list = [PRIORITY_RANK.get(meta.get("priority"), UNSET)]
    if prefer_small:
        key.append(EFFORT_RANK.get(meta.get("effort"), UNSET))
    # Most recently touched first; undated tasks sort last (0 > any -ordinal).
    when = as_date(meta.get("updated")) or as_date(meta.get("created"))
    key.append(-when.toordinal() if when else 0)
    key.append(id_sort_key(meta.get("id")))
    return tuple(key)


def _same_ref(a, b) -> bool:
    """Whether two references point at the same document.

    A bare `42` matches any suffix on number 42, which is what makes
    `--epic 42` keep working on a board whose ids grew suffixes; two explicit
    suffixes have to agree.
    """
    a_number, a_suffix = parse_id(a)
    b_number, b_suffix = parse_id(b)
    if a_number is None or b_number is None or a_number != b_number:
        return False
    return not a_suffix or not b_suffix or a_suffix == b_suffix


def _load_tasks(root: Path, board: str | None = None) -> list[tuple[Path, dict, str]]:
    folder = board_dir(root, "tasks", board)
    out = []
    for p in iter_task_files(folder):
        try:
            meta, body = parse_frontmatter(p.read_text())
        except Exception as exc:
            # Loudly. A task that silently vanishes is worse than a bad sort.
            print(f"warning: skipping {p}: {exc}", file=sys.stderr)
            continue
        if parse_id(meta.get("id"))[0] is None:
            continue
        out.append((p, meta, body))
    return out


def _dep_index(root: Path, board: str | None = None) -> dict:
    """id -> meta over active *and archived* tasks, for resolving depends_on.

    Claim candidates come from the active board, but a dependency that has
    been archived was done or abandoned - i.e. satisfied. Resolving against
    the active board alone meant archiving a finished task silently blocked
    every task that depended on it, forever.
    """
    out = {}
    for _p, meta, _b in iter_docs(root, "tasks", include_archive=True, board=board):
        if parse_id(meta.get("id"))[0] is not None:
            out[str(meta["id"])] = meta
    return out


def _eligible(meta: dict, by_id: dict, args) -> bool:
    if meta.get("status") != "planned":
        return False
    if args.epic is not None and not _same_ref(meta.get("epic"), args.epic):
        return False
    if args.spec is not None and not _same_ref(meta.get("spec"), args.spec):
        return False
    if args.tag and args.tag not in (meta.get("tags") or []):
        return False
    if args.type and meta.get("type") != args.type:
        return False
    for dep in meta.get("depends_on") or []:
        try:
            dep_meta = by_id[resolve_id(dep, by_id)]
        except LookupError as exc:
            # An unresolvable or ambiguous dependency blocks, and says so. A
            # dependency that quietly evaluated to "met" is how a blocked task
            # became claimable.
            print(f"warning: {meta.get('id')}: {exc}", file=sys.stderr)
            return False
        if dep_meta.get("status") not in {"done", "abandoned"}:
            return False
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Find or claim the next available task.")
    p.add_argument("--claim", action="store_true",
                   help="atomically flip status planned -> in-progress")
    p.add_argument("--epic", help="filter by parent epic id (bare number is fine)")
    p.add_argument("--spec", help="filter by spec id (bare number is fine)")
    p.add_argument("--tag")
    p.add_argument("--type", choices=["task", "epic", "bug", "spike"])
    p.add_argument("--root", type=Path)
    p.add_argument("--board", help="board root (default: $TASK_TRACKER_BOARD or 'docs'; "
                                   "empty puts the board at the project root)")
    p.add_argument("--prefer-small", action="store_true",
                   help="rank smaller effort first (off by default: with effort "
                        "in the key, annotating one task reorders it against "
                        "every unannotated one)")
    p.add_argument("--json", dest="as_json", action="store_true")
    p.add_argument("--all", action="store_true",
                   help="list all eligible tasks instead of just the top one")
    args = p.parse_args()

    root = (args.root or find_root()).resolve()
    try:
        width = load_config(root, args.board)["id_width"]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    ctx = board_lock(root, args.board) if args.claim else nullcontext()

    with ctx:
        tasks = _load_tasks(root, args.board)
        by_id = _dep_index(root, args.board)
        eligible = [(p, m, b) for p, m, b in tasks if _eligible(m, by_id, args)]
        eligible.sort(key=lambda t: _rank(t[1], args.prefer_small))

        if not eligible:
            if args.as_json:
                print(json.dumps(None))
            else:
                print("(no eligible task)", file=sys.stderr)
            return 2

        chosen = eligible if args.all else eligible[:1]

        if args.claim:
            path, meta, body = chosen[0]
            meta["status"] = "in-progress"
            meta["updated"] = date.today().isoformat()
            path.write_text(dump_frontmatter(meta, body))

    # Nothing cites a handoff and it no longer sits beside the charter, so
    # opening the task cannot reveal it. Surfacing it here is what replaces
    # stumbling over the file: this is the moment you are about to resume.
    def _handoff(meta):
        h = handoff_path(root, meta["id"], args.board)
        return h if h.is_file() else None

    if args.as_json:
        payload = [
            {"id": display_id(m["id"], width), "title": m.get("title"), "path": str(p),
             "status": m.get("status"), "type": m.get("type"),
             "epic": m.get("epic"), "spec": m.get("spec"),
             "handoff": (str(h) if (h := _handoff(m)) else None)}
            for p, m, _ in chosen
        ]
        print(json.dumps(payload if args.all else payload[0]))
    else:
        for path, meta, _ in chosen:
            idv = display_id(meta["id"], width)
            print(f"{idv}  {meta.get('status', '?'):11}  {meta.get('title', '')}")
            print(f"        {path}")
            if (h := _handoff(meta)):
                print(f"        handoff: {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
