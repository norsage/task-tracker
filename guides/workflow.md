# Workflow

The board is a directory of markdown files. Frontmatter is the structured
view (status, links, tags); the body is the narrative. Everything else
follows from that.

## Artifacts

- **Spec** (`docs/specs/NNNN.xxx-slug.md`) — the starting document for a piece
  of work. Engineering/research-flavoured: context, question, approach,
  evaluation. Optional for small mechanical work.
- **Task** (`docs/tasks/NNNN.xxx-slug.md`, `type: task`) — one concrete unit of
  work. One file per task; never bundle.
- **Epic** (`type: epic`) — a container task. Has children (`epic: <id>`
  on each child points up). Tracked but not "worked on" directly.
- **Bug** (`type: bug`) — has Repro / Expected / Actual / Investigation.
- **Spike** (`type: spike`) — timeboxed investigation; the deliverable is
  Findings, not code.

Specs and tasks have **separate ID counters**. Both start at 1.

## IDs

An id is `NNNN.xxx`: a sequential number plus a random discriminator, e.g.
`0042.k3f`. The two halves do different jobs.

The **number** is allocated locally as max+1. No coordination, which is why
two branches forked from the same commit both mint 0042, and why tasks
created in one sitting stay adjacent, so `ls` reads chronologically and
related work clusters.

The **discriminator** is what makes the pair distinguishable after those
branches merge. Both files survive, both stay individually addressable, and
nothing silently misresolves.

References resolve git-style. A bare `42` works while the board holds one 42:

```
next.py --all --epic 42          # fine
new.py task "..." --depends-on 42
```

Once the board holds two, the same reference errors with both candidates and
you disambiguate with `--depends-on 42.k3f`. `new.py` stores the *resolved*
full id, so a reference written today never goes ambiguous later.

So bare numbers are for conversation and CLI args only. Anything committed
(source comments, commit messages, bodies, frontmatter) carries the suffix,
and refers to an item already on the board. `refs.py --check` enforces this.
Under `suffix_length: 0` there is no suffix to write and no check to run.

Width lives in `.task-tracker.md` at the board root:

```markdown
---
suffix_length: 3     # 0042.k3f
id_width: 4
archive_after_days: 14
---
```

Commit that file. `suffix_length` is a wire format rather than a preference:
every writer on the board must use the same one, and mixing 0 with a nonzero
width is the one unsafe combination: a bare `0042` is then both a valid id
*and* a prefix of `0042.k3f`, which is the ambiguity the discriminator exists
to prevent. Sizing, as P(collision) for k branches contesting one number:

| width | k=2 | k=3 | k=10 | k=10 creating 10 tasks each |
| ----- | --- | --- | ---- | --------------------------- |
| 2 | 0.098% | 0.29% | 4.3% | 36% |
| 3 | 0.003% | 0.009% | 0.14% | 1.4% |
| 4 | 0.0001% | 0.0003% | 0.004% | 0.04% |

A collision means "redraw a suffix", not "corrupted board": `index.py --check`
fails on duplicate ids and prints both paths. Raising the width later is free,
since numbers never overlap across time: old bare ids coexist with new
suffixed ones.

`suffix_length: 0` restores plain `0042` ids. Only safe on a genuinely
single-writer board, and note that solo is not single-writer: worktrees, a
second machine, or a swarm of agents under one git identity are all concurrent
writers.

## Lifecycle

```
spec(draft) → spec(active) → ... → spec(archived)
                  │
                  ▼
task(planned) → task(in-progress) → task(done)
                       ↑                  │
                  task(blocked)            ▼
                                       (archive after N days)
                  task(abandoned) ─────────┘
```

Status values:

- **Task**: `idea`, `planned`, `in-progress`, `blocked`, `done`, `abandoned`
- **Spec**: `draft`, `active`, `archived`

`blocked` is for items that were picked up but can't progress until
something external resolves. It keeps them visible above `planned` items
in queues without losing the "we already started" signal.

## Frontmatter

Required on every artifact: `id`, `title`, `status`, `created`, `updated`.
Tasks/epics/bugs/spikes also require `type`. Optional fields are *omitted
when null*; don't leave `tags: null` lying around.

Optional fields (use as needed):

| field          | purpose                                              |
| -------------- | ---------------------------------------------------- |
| `description`  | one-liner shown in lists/UIs                         |
| `tags`         | flat list of strings                                 |
| `priority`     | `low` / `medium` / `high`                            |
| `effort`       | `S` / `M` / `L`                                      |
| `epic`         | id of parent epic                                    |
| `spec`         | id of spec this implements                           |
| `depends_on`   | list of task ids that must reach `done`/`abandoned` |
| `related`      | loose pointers ("see also")                          |
| `related_tasks`| same, on specs                                       |
| `blocked_by`   | free-text reason when `status: blocked`              |

## Coordination between agents

The frontmatter *is* the coordination channel. Multiple Claude Code
sessions on the same checkout share the board.

- `status: in-progress` is the claim. If you see it, the task is taken;
  pick another.
- `next.py --claim` performs the planned → in-progress transition under
  a single board-wide file lock (`docs/tasks/.tt.lock`, `fcntl.flock`).
  Two simultaneous claims get different tasks; no collision possible.
- The lock auto-releases on process exit (kernel semantics), so a crashed
  agent never freezes the board. The task it was working on stays
  `in-progress`; flip it back to `planned` if needed.
- Body edits (Notes, Findings) are *not* under the lock. Two agents
  editing the same task body simultaneously will conflict in git, same
  as any other concurrent edit.

There is no agent identity. We don't track *who* is working on what,
only that something is in progress. `git log` answers attribution if you
ever need it.

## Archival

Items with terminal status (`done`, `abandoned`, `archived`) older than N
days (default 14) move to `docs/{tasks,specs}/archive/YYYY-MM/` via
`archive.py`. A one-line summary is appended to
`archive/digest-YYYY-MM.md`.

Digests are *append-only* and **never** deleted. Individual archived
files can be pruned with `--prune-older-than-days N` once they stop being
useful; the digest preserves the historical record.

IDs of archived items are not reused (`new.py` scans archives when
allocating).
