---
name: task-tracker
description: Markdown-based task board for research and engineering projects. Use whenever the user wants to plan, track, or work through tasks/epics/bugs/spikes, or when the project contains `docs/specs/` or `docs/tasks/` directories with frontmatter'd markdown files. Coordinates multiple agent sessions on the same checkout via per-task status and a board lock.
---

# Task Tracker

You are working with a markdown-only task tracker. The whole board lives
under `docs/` in the user's project:

```
docs/
├── .task-tracker.md        # board settings (committed; see "IDs" below)
├── specs/                  # starting documents (research/engineering, not PRDs)
│   ├── NNNN.xxx-slug.md
│   └── archive/
└── tasks/                  # tasks, epics, bugs, spikes (all type-tagged)
    ├── NNNN.xxx-slug.md
    └── archive/
```

Frontmatter is structured state; the body is narrative. Specs and tasks
have **separate ID counters**, both zero-padded to 4 digits in filenames.

## When to do what

### User describes a new initiative

1. Ask whether it warrants a **spec** first. Default: yes if the work is
   non-trivial, multi-task, exploratory, or research-flavoured. No if
   it's a small mechanical change.
2. If yes, create the spec with `scripts/new.py spec "<title>"`. Open
   the resulting file and fill in: Context, Question/Goal, Approach,
   Out of scope, Risks & unknowns, Evaluation, References.
3. Discuss the spec with the user before generating tasks. Treat it as
   draft until they say it's good, then flip `status: active`.

### User wants to break a spec into tasks

1. Read the spec.
2. Propose a task list, one task per concrete unit of work. If the
   spec is large, propose an **epic** first (`new.py epic "..."`) and
   then child tasks linked with `--epic <id>`.
3. Create each task with `new.py task "<title>" --spec <id> [--epic <id>] [--depends-on ...] [--priority ...] [--effort ...]`.
4. After creating tasks, update the epic's "Child tasks" section to
   list them.

### User says "work on X" or "take the next task"

1. Run `scripts/next.py --claim` (optionally with `--epic`, `--spec`,
   `--tag`, `--type`). This atomically flips the chosen task's status
   to `in-progress` under a board-wide flock, so it's safe even if
   another Claude session is doing the same thing.
2. Read the task file; do the work.
3. Append findings to the **Notes** section as you go.
4. When done: set `status: done`, bump `updated`, save. If you hit a
   wall: `status: blocked` plus `blocked_by: "<reason>"`.

### User wants to see what's going on

- `index.py --board ''` regenerates `tasks/_index.md`, the generated view over
  every task grouped by status. Never hand-edit it; `--check` fails if stale.
- `next.py --all` lists currently eligible (planned + deps met) tasks,
  ranked by priority, then most-recently-updated, then id. Unset fields
  sort *after* every explicit value, so annotating one task never demotes
  it below the ones nobody has annotated. `effort` joins the key only
  behind `--prefer-small`, for the same reason.
- `next.py --all --json` for structured output.
- Plain `ls docs/tasks/*.md` + reading frontmatter works too.
- `grep -l 'status: in-progress' docs/tasks/*.md` to see what's claimed.

### Board location and settings

The board defaults to `docs/{tasks,specs}/`. Where `docs/` already means
something else (reproduction documentation, say), point it elsewhere with
`$TASK_TRACKER_BOARD` or `--board`. An empty value puts the board at the
project root, i.e. `tasks/`. Every script takes `--board`.

Board *location* is local (one dev's `docs/` may mean something else), so it
stays an env var or flag. Board *settings* are shared, and live in
`.task-tracker.md` at the board root. Commit it:

| key | default | what it does |
| --- | ------- | ------------ |
| `suffix_length` | 3 | chars of random discriminator: `0042.k3f`. 0 disables |
| `id_width` | 4 | zero-padding of the number |
| `archive_after_days` | 14 | `archive.py` default |

`suffix_length` is the one that must match across every writer. Read the IDs
section of `guides/workflow.md` before changing it. `templates/config.md` is a
commented starting point; the defaults apply with no file present.

### IDs

Ids look like `0042.k3f`. The number is sequential (so tasks created together
stay adjacent); the suffix keeps two branches from both minting a task called
0042. Refer to a task by the shortest unambiguous form: `42` until the board
holds two, then `42.k3f`. `index.py --check` fails on duplicate ids, which is
what a bad merge looks like.

### User says "clean up" or "archive done items"

Run `scripts/archive.py`. Done/abandoned items older than 14 days move
to `archive/YYYY-MM/` and get a one-line entry in `archive/digest-YYYY-MM.md`.
Digests are append-only and never deleted by the script.

To delete individual archived files (digests preserved):
`archive.py --prune-older-than-days 365`.

## Behavioural rules

- **One task per unit, in one of two shapes.** `NNNN-slug.md` for a task
  that fits in a file; `NNNN-slug/README.md` for one that grows an
  evidence trail (logs, plots, scratch analyses), with the frontmatter
  in the README. Never bundle two tasks into one file, and never let a
  second task's state accumulate inside another's directory. Archiving a
  directory-shaped task moves the whole directory, evidence included.
- **Start file-shaped; promote when evidence appears.** You cannot tell
  at filing time which shape a task needs, so don't try: file it as a
  `.md` and run `scripts/promote.py <id>` when it grows one. That does
  the `git mv` and fixes the links the move breaks: relative links in
  the charter shift a level, inbound links gain `/README.md`, and
  neither breaks loudly if done by hand. `new.py task --dir` is for the
  rare case you already know. **Needing a handoff is not a reason to
  promote**; see below.
- **Resume state lives at `tasks/_handoffs/<id>.md`**, for both shapes,
  keyed by the full id so a retitle can't orphan it. Gitignore that
  directory: the file is overwritten every session and versioning it
  versions noise. Nothing durable may live there and nothing may cite
  it, which is exactly why it doesn't need to sit beside the charter.
  `next.py` prints the path when it surfaces a task, and `archive.py`
  deletes it on archive. `ls docs/tasks/_handoffs/` is the list of
  everything mid-flight.
- **Record where knowledge exits.** A task closes into something else:
  its artifacts belong in canonical homes, listed in the `exits:`
  frontmatter field, and written there *as they are produced* rather
  than at the end. A closed task whose artifacts are all still inside
  its own directory was mis-filed.
- **Start the title with a phrase that survives being cut at four words.**
  The slug is the title's first four words, chopped mechanically: "Repo
  reorg: the close-out handoff" gives `repo-reorg-the-close-out`. Drop the
  filler: "Repo reorg close-out handoff" gives `repo-reorg-close-out-handoff`,
  whole. Read the slug `new.py` prints; if it ends mid-phrase, reword the
  title, don't rename the file.
- **Filenames are English, whatever the title's language.** A title in
  another language (a Russian board) needs `--slug` with three or four
  English words; `new.py` refuses it without one. The title and body stay
  in the board's language.
- **Omit empty optional frontmatter fields.** Don't leave `tags: null`
  or `epic: null` behind.
- **Bump `updated`** every time you change a task's frontmatter or
  status. The scripts do this automatically; if you edit by hand,
  remember.
- **Don't reuse IDs, and never hand-assign one.** Always use `new.py`: it
  scans active + archive for the next free number and draws the random
  discriminator that keeps concurrent branches apart.
- **Never refer to an item that isn't on the board.** Need an id for
  something unwritten? File it first with `new.py bug "<title>"` (title-only
  is fine), then use the id it prints. Never predict a number.
- **Committed references carry the suffix**: `0042.k3f` in source comments,
  commit messages, bodies and frontmatter. A bare `42` is for conversation
  and CLI args only. Never resolve an ambiguous reference by guessing which
  one was meant. Ask, or read both.
- **Run `refs.py --check`** before committing anything with task references.
- **Don't rename files** unless the user explicitly asks. The slug in
  the filename is a hint; the canonical identifier is the `id` in
  frontmatter.
- **The Notes section is durable.** Treat it as the log future agents
  read to pick up where you left off. Negative results matter: record
  what didn't work.
- **No agent identity.** The board doesn't track who is working on what,
  only that something is in progress. Don't add `owner:` or similar.
- **Respect `depends_on`.** Don't claim a task whose deps aren't `done`
  or `abandoned`. `next.py` handles this; if you're picking by hand,
  check.
- **Spec language is research/engineering, not product.** Use Context,
  Question/Goal, Approach, Evaluation. Avoid "success criteria",
  "acceptance criteria", "user stories", "business value".

## Reference

- `guides/workflow.md` — full workflow, statuses, archival semantics, IDs
- `guides/writing-specs.md` — what goes in a spec, when to skip
- `guides/writing-tasks.md` — task granularity, types, body sections
- `templates/{spec,task,epic,bug,spike}.md` — the templates `new.py` uses
- `templates/config.md` — commented `.task-tracker.md` to copy

## Scripts

All scripts live in this skill's `scripts/` directory and are
zero-dependency Python 3. Invoke with `python3 <skill>/scripts/<name>.py`.

| script        | purpose                                                    |
| ------------- | ---------------------------------------------------------- |
| `new.py`      | Create a spec/task/epic/bug/spike; atomic ID allocation    |
| `next.py`     | Find or claim the next eligible task (deps + filters)      |
| `promote.py`  | File-shaped task -> directory; fixes the links it breaks   |
| `archive.py`  | Move terminal items to archive; update monthly digests     |
| `index.py`    | Regenerate `tasks/_index.md`; `--check` fails if stale     |
| `refs.py`     | Check committed references carry a suffix and resolve      |

All of them accept `--root <path>` to override project-root auto-detection,
which walks up from cwd looking for `docs/{tasks,specs}/`, then falls
back to common project markers (`.git`, `pyproject.toml`), then to cwd.
