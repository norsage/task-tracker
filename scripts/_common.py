"""Shared helpers for task-tracker scripts.

Kept zero-dependency on purpose: a minimal frontmatter parser/dumper for the
schema we control, a project-root finder, atomic-ID allocation, and a flock
context manager. If you need richer YAML, replace _parse_value / _dump_value
with PyYAML; the rest is portable.

IDs are `NNNN.xxx` - a sequential number plus a random discriminator. The
number is allocated locally as max+1, so tasks created in one sitting stay
adjacent; the discriminator is what keeps two branches that never saw each
other from both minting a task called 0042. References resolve git-style: a
bare `42` works while it is unambiguous, and errors listing candidates when it
is not. Width is set per board in `.task-tracker.md` and must be the same for
every writer - see load_config.
"""
from __future__ import annotations

import fcntl
import os
import re
import secrets
from contextlib import contextmanager
from pathlib import Path

TASK_TYPES = ("task", "epic", "bug", "spike")
TASK_STATUSES = ("idea", "planned", "in-progress", "blocked", "done", "abandoned")
SPEC_STATUSES = ("draft", "active", "archived")

# base36 minus 0/1/l/o - the glyph pairs that get misread when someone copies
# an id out of a filename by hand. 32 symbols, so each character is 5 bits.
SUFFIX_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"

CONFIG_NAME = ".task-tracker.md"

# suffix_length is a wire format, not a preference: every writer on a board
# must use the same one. Mixing 2 and 3 is harmless (both are full ids), but
# mixing 0 with anything else makes a bare `0042` both a valid id *and* a
# prefix of `0042.k3f`, which is the exact ambiguity the suffix exists to
# prevent. That is why this file belongs in the repo and not in a local
# override: a private setting cannot express an agreement between writers.
DEFAULTS = {
    "suffix_length": 3,
    "id_width": 4,
    "archive_after_days": 14,
}
_LIMITS = {
    "suffix_length": (0, 8),
    "id_width": (1, 8),
    "archive_after_days": (0, 100000),
}


def find_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default: cwd) looking for an existing board
    directory or a common project marker. Fall back to cwd.
    """
    start = (start or Path.cwd()).resolve()
    board = os.environ.get("TASK_TRACKER_BOARD", "docs").strip().strip("/")
    for candidate in (start, *start.parents):
        base = (candidate / board) if board else candidate
        if (base / "tasks").is_dir() or (base / "specs").is_dir():
            return candidate
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return start


def as_date(v):
    """Parse an ISO date out of frontmatter; None when absent or malformed."""
    from datetime import date, datetime

    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except Exception:
        return None


_SLUG_RE = re.compile(r"[^\w\s-]")


def slugify(title: str, max_words: int = 4) -> str:
    s = _SLUG_RE.sub("", title.lower()).strip()
    words = s.split()[:max_words]
    return "-".join(words) or "untitled"


# --- config -------------------------------------------------------------

def load_config(root: Path, board: str | None = None) -> dict:
    """Board settings from `<board root>/.task-tracker.md` frontmatter.

    Lives at the board root rather than inside `tasks/` because the spec and
    task counters share it, and because `iter_task_files` only skips `_` and
    `digest-` prefixes - a config file inside a kind directory would be read
    as a task.
    """
    cfg = dict(DEFAULTS)
    path = board_root(root, board) / CONFIG_NAME
    if path.is_file():
        try:
            meta, _ = parse_frontmatter(path.read_text())
        except Exception as exc:
            raise ValueError(f"{path}: {exc}") from None
        for key in DEFAULTS:
            if key not in meta or meta[key] is None:
                continue
            value = meta[key]
            lo, hi = _LIMITS[key]
            # Loudly. A board that silently fell back to the default width
            # would hand out ids in a format its neighbours do not expect.
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{path}: {key} must be an integer, got {value!r}")
            if not lo <= value <= hi:
                raise ValueError(f"{path}: {key} must be in {lo}..{hi}, got {value}")
            cfg[key] = value
    return cfg


# --- ids ----------------------------------------------------------------

_ID_RE = re.compile(r"^0*(\d+)(?:\.([a-z0-9]+))?$")
# Filenames carry the id as a prefix: 0042.k3f-train-baseline.md
_FILENAME_ID_RE = re.compile(r"^(\d+)(?:\.([a-z0-9]+))?-")


class AmbiguousId(LookupError):
    """A reference matched more than one document, git-style."""

    def __init__(self, query, candidates):
        self.query = query
        self.candidates = list(candidates)
        super().__init__(
            f"ambiguous id {query!r}: matches {', '.join(self.candidates)}"
        )


def parse_id(value) -> tuple[int | None, str]:
    """(number, suffix) from an id or a reference; (None, '') if unparseable.

    Accepts the int form too, so a hand-written `epic: 42` still resolves and
    boards created before ids carried suffixes keep working.
    """
    if value is None or isinstance(value, bool):
        return None, ""
    if isinstance(value, int):
        return value, ""
    m = _ID_RE.match(str(value).strip())
    if not m:
        return None, ""
    return int(m.group(1)), (m.group(2) or "")


def format_id(number: int, suffix: str = "", id_width: int = 4) -> str:
    base = f"{number:0{id_width}d}"
    return f"{base}.{suffix}" if suffix else base


def gen_suffix(length: int) -> str:
    """A random discriminator. Random, not derived from author identity: two
    branches by the same author would draw the same derived value every time.
    """
    return "".join(secrets.choice(SUFFIX_ALPHABET) for _ in range(length))


def display_id(value, id_width: int = 4) -> str:
    """Canonical rendering of a stored id.

    Boards written before ids carried suffixes stored the number as a plain
    int, so `id: 2` has to print as `0002` to line up with its own filename
    and with its suffixed neighbours.
    """
    number, suffix = parse_id(value)
    if number is None:
        return str(value)
    return format_id(number, suffix, id_width)


def id_sort_key(value) -> tuple:
    """Sort by number then suffix. Unparseable ids sort last."""
    number, suffix = parse_id(value)
    return (10 ** 9 if number is None else number, suffix)


def resolve_id(query, ids):
    """Resolve a reference against known ids, git-style.

    An exact id wins outright. Otherwise the query's number must match and its
    suffix must be a prefix of the candidate's, so `42` finds `0042.k3f` while
    the board holds only one 42, and raises once it holds two.
    """
    ids = list(ids)
    text = None if query is None else str(query).strip()
    if text is not None:
        for cand in ids:
            if str(cand) == text:
                return cand

    number, suffix = parse_id(query)
    if number is None:
        raise LookupError(f"unparseable id reference: {query!r}")

    hits = []
    for cand in ids:
        c_number, c_suffix = parse_id(cand)
        if c_number != number:
            continue
        if suffix and not c_suffix.startswith(suffix):
            continue
        hits.append(cand)

    if not hits:
        raise LookupError(f"no such id: {query}")
    if len(hits) > 1:
        raise AmbiguousId(query, sorted(str(h) for h in hits))
    return hits[0]


# --- frontmatter --------------------------------------------------------

_FIELD_ORDER = (
    "id", "title", "type", "status", "created", "updated",
    "description", "tags", "priority", "effort",
    "epic", "spec", "depends_on", "related", "related_tasks", "blocked_by",
    # Where this task's knowledge left to. A closed task whose artifacts are
    # all still inside its own directory was mis-filed, so the close check is
    # "exits is non-empty and every path in it exists".
    "exits",
)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    fm_text = "".join(lines[1:end])
    body = "".join(lines[end + 1:])
    meta: dict = {}

    fm_lines = fm_text.splitlines()
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # A sequence item with no owning key. Dropping it is how an unmet
        # dependency used to become an empty dependency list, which made a
        # blocked task claimable. Fail loudly instead.
        if stripped.startswith("- "):
            raise ValueError(
                f"frontmatter: list item {stripped!r} has no owning key"
            )

        if ":" not in line:
            raise ValueError(f"frontmatter: cannot parse line {stripped!r}")

        k, _, v = line.partition(":")
        key, v = k.strip(), v.strip()

        # `key:` on its own may introduce a block sequence:
        #     depends_on:
        #       - 12
        if v == "":
            items, j = [], i + 1
            while j < len(fm_lines):
                s = fm_lines[j].strip()
                if s.startswith("#"):
                    j += 1
                    continue
                if not s.startswith("- "):
                    break  # blank line or next key ends the sequence
                items.append(_parse_scalar(s[2:].strip()))
                j += 1
            if items:
                meta[key] = items
                i = j
                continue

        meta[key] = _parse_value(v)
        i += 1

    return meta, body


def dump_frontmatter(meta: dict, body: str) -> str:
    lines = ["---"]
    seen = set()
    for k in _FIELD_ORDER:
        if k in meta and not _is_empty(meta[k]):
            lines.append(f"{k}: {_dump_value(meta[k])}")
            seen.add(k)
    for k, v in meta.items():
        if k in seen or _is_empty(v):
            continue
        lines.append(f"{k}: {_dump_value(v)}")
    lines.append("---")
    body = body.lstrip("\n")
    out = "\n".join(lines) + "\n\n" + body
    if not out.endswith("\n"):
        out += "\n"
    return out


def _is_empty(v) -> bool:
    return v is None or v == "" or v == []


def _parse_value(v: str):
    if v == "" or v.lower() in {"null", "~"}:
        return None
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x.strip()) for x in inner.split(",")]
    return _parse_scalar(v)


def _parse_scalar(v: str):
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def _dump_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_dump_scalar(x) for x in v) + "]"
    return _dump_scalar(v)


_NUMERIC_RE = re.compile(r"-?\d+")


def _dump_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # Quote a string that would read back as an int, or `id: "0042"` loses its
    # padding the first time a claim rewrites the frontmatter.
    if any(c in s for c in ":#[]{}\"") or _NUMERIC_RE.fullmatch(s):
        return '"' + s.replace('"', '\\"') + '"'
    return s


# --- doc discovery & ID allocation --------------------------------------

def board_root(root: Path, board: str | None = None) -> Path:
    """The directory holding `tasks/`, `specs/` and `.task-tracker.md`."""
    if board is None:
        board = os.environ.get("TASK_TRACKER_BOARD", "docs")
    board = board.strip().strip("/")
    return (root / board) if board else root


def board_dir(root: Path, kind: str, board: str | None = None) -> Path:
    """Where the board lives. Configurable because `docs/` is already taken in
    some projects (there it means reproduction documentation, not a task board).

    Order: explicit argument, then $TASK_TRACKER_BOARD, then "docs". An empty
    value puts the board at the project root, i.e. <root>/tasks.
    """
    return board_root(root, board) / kind


HANDOFF_DIR = "_handoffs"


def handoff_path(root: Path, task_id, board: str | None = None) -> Path:
    """Where a task's resume state lives: `tasks/_handoffs/<id>.md`.

    Board-level rather than beside the charter, because a handoff is
    gitignored, rewritten every session and may never be cited - so nothing
    links to it, and its location is free. Keeping them together means one
    gitignore line, one place to see everything mid-flight, and one known path
    to delete on archive. Keyed by the full id, not the slug, so a retitle
    cannot orphan it.
    """
    return board_dir(root, "tasks", board) / HANDOFF_DIR / f"{task_id}.md"


def iter_task_files(folder: Path, recurse_archive: bool = False):
    """Yield every task document in `folder`, in both supported shapes.

    A one-file task is `NNNN.xxx-slug.md`. A task that grew state is
    `NNNN.xxx-slug/README.md` with the frontmatter in the README - the shape a
    multi-session task needs so its handoff, evidence and work list can sit
    beside the charter.
    """
    if not folder.is_dir():
        return
    for p in sorted(folder.glob("*.md")):
        # pathlib's glob matches dotfiles, unlike the shell's, so a stray
        # `.something.md` would otherwise be parsed as a task.
        if p.name.startswith((".", "_", "digest-")):
            continue
        yield p
    for d in sorted(folder.iterdir()):
        if not d.is_dir() or d.name == "archive" or d.name.startswith((".", "_")):
            continue
        readme = d / "README.md"
        if readme.is_file():
            yield readme
    if recurse_archive:
        archive = folder / "archive"
        if archive.is_dir():
            for p in sorted(archive.rglob("*.md")):
                if p.name.startswith((".", "digest-")) or p.name == "README.md":
                    continue
                yield p
            for readme in sorted(archive.rglob("*/README.md")):
                yield readme


def iter_docs(root: Path, kind: str, include_archive: bool = True,
              board: str | None = None):
    """Yield (path, meta, body) for all docs of the given kind ('tasks' | 'specs')."""
    folder = board_dir(root, kind, board)
    for p in iter_task_files(folder, recurse_archive=include_archive):
        yield from _maybe_yield(p)


def _maybe_yield(p: Path):
    try:
        meta, body = parse_frontmatter(p.read_text())
    except Exception as exc:
        # Never swallow this. A skipped task is invisible, and invisible is
        # exactly how a malformed dependency list used to pass the gate.
        import sys

        print(f"warning: skipping {p}: {exc}", file=sys.stderr)
        return
    yield p, meta, body


def all_ids(root: Path, kind: str, board: str | None = None) -> list[str]:
    """Every id of the given kind, active and archived, for id resolution."""
    out = []
    for _, meta, _ in iter_docs(root, kind, board=board):
        if parse_id(meta.get("id"))[0] is not None:
            out.append(str(meta["id"]))
    return out


def next_id(root: Path, kind: str, board: str | None = None) -> int:
    """Highest existing id number (active + archive + filename prefix) + 1.

    Still purely local: no coordination, so two branches forked from the same
    commit both return the same number. The suffix is what separates them.
    """
    max_id = 0
    for _, meta, _ in iter_docs(root, kind, board=board):
        i, _suffix = parse_id(meta.get("id"))
        if i is not None and i > max_id:
            max_id = i
    folder = board_dir(root, kind, board)
    if folder.is_dir():
        # Filename prefixes too, so a half-written task still burns its ID.
        # Only real task documents count: the archive's YYYY-MM/ buckets also
        # start with digits and a dash, and scanning them blindly allocated
        # id 2027 off a directory named 2026-07.
        candidates = list(folder.rglob("*.md"))
        candidates += [d for d in folder.rglob("*") if d.is_dir() and (d / "README.md").is_file()]
        for p in candidates:
            m = _FILENAME_ID_RE.match(p.name)
            if m:
                i = int(m.group(1))
                if i > max_id:
                    max_id = i
    return max_id + 1


def allocate_id(root: Path, kind: str, cfg: dict, board: str | None = None) -> str:
    """The next id, suffix included. Call under `board_lock`.

    The suffix is redrawn if it clashes with an id already on this board, so
    collisions within one checkout are impossible and only the cross-branch
    case is left to chance.
    """
    number = next_id(root, kind, board)
    width = cfg.get("id_width", DEFAULTS["id_width"])
    length = cfg.get("suffix_length", DEFAULTS["suffix_length"])
    if length <= 0:
        return format_id(number, "", width)

    taken = {str(i) for i in all_ids(root, kind, board)}
    for _ in range(100):
        candidate = format_id(number, gen_suffix(length), width)
        if candidate not in taken:
            return candidate
    raise RuntimeError(
        f"could not draw a free {length}-char suffix for id {number}; "
        f"raise suffix_length in {CONFIG_NAME}"
    )


def find_duplicate_ids(root: Path, kind: str, board: str | None = None) -> dict:
    """{id: [paths]} for ids held by more than one document.

    This is what a bad merge looks like: before ids carried suffixes two
    branches could both mint 0042, the files merged cleanly because their slugs
    differed, and `depends_on: 42` then resolved to whichever one was read
    last. Fail the board check instead.
    """
    seen: dict[str, list[Path]] = {}
    for p, meta, _ in iter_docs(root, kind, board=board):
        if parse_id(meta.get("id"))[0] is None:
            continue
        seen.setdefault(str(meta["id"]), []).append(p)
    return {k: v for k, v in seen.items() if len(v) > 1}


# --- locking ------------------------------------------------------------

@contextmanager
def board_lock(root: Path, board: str | None = None):
    """Exclusive lock on the board for the duration of a claim transaction.

    Held briefly (read directory, write one file). Auto-released on process
    exit via fcntl semantics, so a crashed agent never freezes the board.

    Scoped to one checkout: this is what makes concurrent agents on a shared
    working tree safe, and what cannot help two separate clones - hence the id
    suffix.
    """
    lock_dir = board_dir(root, "tasks", board)
    lock_dir.mkdir(parents=True, exist_ok=True)
    # Outside the repository on purpose: a lock file inside it shows up in
    # `git status`, and tools that refuse or flag a dirty tree (a remote run
    # of the committed tree, a run tracker's git.dirty tag) would trip on the
    # act of claiming a task. One lock per board directory, keyed by its path.
    import hashlib
    import tempfile
    digest = hashlib.sha256(str(lock_dir.resolve()).encode()).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"task-tracker-{digest}.lock"
    with open(lock_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
