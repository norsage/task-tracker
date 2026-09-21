# Writing tasks

A task is one unit of work. One file per task; never bundle. The file's
body is where context, steps, and findings accumulate; the frontmatter
is the structured view (status, links, tags).

## Picking the right type

| type    | when to use                                                    |
| ------- | -------------------------------------------------------------- |
| `task`  | default; concrete unit of implementation work                  |
| `epic`  | container for several related tasks; not worked on directly    |
| `bug`   | something is broken; needs repro + investigation               |
| `spike` | timeboxed exploration; deliverable is *findings*, not code     |

If you find yourself describing several things in one task, it's
probably an epic. Create the epic, then split.

## Granularity

Aim for tasks that one agent can complete in a single session without
needing to re-plan mid-way. Signs a task is too big:

- the title contains "and"
- the Steps list has more than ~5 entries
- you can't predict what state the repo will be in when it's done

Signs it's too small:

- the title is the entire task ("fix typo in README")
- it has no Notes worth keeping after merge

## Filling in the body

The body sections in the template are prompts to help an agent think,
not structure to preserve at all costs. Edit freely. The one section
worth always keeping is **Notes**: that's the durable log that future
tasks and agents read.

### Context

Why this task exists. What an agent picking it up *cold* needs to know
before starting. Link the spec/epic, prior tasks, constraints, decisions
already made.

### Steps

A checklist the executing agent ticks through. Concrete and verifiable;
prefer "run X and inspect Y" over "investigate Z".

### Notes

Findings, surprises, decisions, dead ends. Update as you work; this is
the part downstream readers rely on. Negative results matter.

## Dependencies and links

- `depends_on: [<ids>]` — hard prerequisite; `next.py` will skip this
  task until its deps reach `done`/`abandoned`.
- `epic: <id>` — points up at the parent epic.
- `spec: <id>` — points back at the spec this implements.
- `related: [<ids>]` — soft link; "see also".
- `blocked_by: "free text"` — paired with `status: blocked`; describe
  what's blocking in prose (waiting on data, external team, etc.).

## Status transitions

```
planned ──claim──▶ in-progress ──complete──▶ done
   ▲                    │
   │                    └──hit a wall──▶ blocked ──unblocked──▶ in-progress
   │                                        │
   └────────────reopen────────────  abandoned ◀──give up──┘
```

Bump `updated` on every transition. The script does this for you when
you use `next.py --claim`.

## Bug-specific body sections

- **Repro**: smallest reliable way to make the bug appear
- **Expected** / **Actual**: the contrast
- **Investigation**: hypotheses tried, evidence; where most of the
  durable value lives
- **Resolution**: what fixed it (or why we chose not to fix); link the
  commit/PR

## Spike-specific body sections

- **Question**: what we want to find out
- **Timebox**: how long before we stop and write down what we know
- **Findings**: what we learned, including negative results
- **Follow-ups**: tasks/epics/spikes surfaced (linked by id)
