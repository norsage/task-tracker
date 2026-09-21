# task-tracker

Keeps the board for a project that several agent sessions work on at once:
what is planned, what someone has already picked up, and what each piece of
work was for. Markdown beside the code, one file per item. Use when a project
needs a task board, or already has one.

The starting document is a spec: Context, Question, Approach, Evaluation. The
work under it is tasks, epics, bugs and spikes.

## Install

```sh
git clone https://github.com/norsage/task-tracker.git && TT=$PWD/task-tracker

bash $TT/install.sh            # every project on this machine
bash $TT/install.sh --symlink  # link the clone: the agent reads your checkout

cd my-project
bash $TT/install.sh --project  # into the current directory, committed with this project
```

Re-running replaces the install, after a prompt.

## Using it

Start your agent in the project's directory and say what you want.

> *"We need a pipeline from raw logs to an evaluation report. Let's design it."*

It drafts a spec and you work on that file together until it says what you
meant. Everything else hangs off it.

| Kind | You say | Holds |
|---|---|---|
| spec | *"We need a pipeline from raw logs to an evaluation report. Let's design it."* | the question a piece of work is meant to answer, and how you'd know |
| task | *"Generate tasks from the spec."* | one unit of work, small enough to finish without re-planning |
| epic | *"Group the ingest tasks under one epic."* | a container for related tasks |
| bug | *"The loader drops the last batch. File it."* | a repro, what was expected, and what was tried |
| spike | *"Find out whether the new API can do this at all."* | a question with a deadline instead of a deliverable |

Open a second session and a third, and each gets a different task:

> *"Take the next ingest task."*

Two sessions asking at the same moment cannot win the same task. Keep the
checkout local: file locks over NFS and sshfs are unreliable.

When work concludes the skill sweeps it into a dated archive and adds a line
to that month's digest. The files can be deleted later; the digests stay.

## Customising

The templates in `templates/` are starting points — edit them to match the way
you actually write specs and tasks, and the scripts read them at runtime, so
changes take effect immediately.

The frontmatter schema is enforced loosely: anything you add survives the
round-trip. Add fields as you need them, and say what the new one means in
`guides/workflow.md`.

## Reading further

- [`SKILL.md`](SKILL.md) — the rules the agent follows: when to write what, the
  frontmatter, the ids, and the scripts
- [`guides/workflow.md`](guides/workflow.md) — statuses, archival, and the id
  scheme in full, including how wide to make the suffix
- [`guides/writing-specs.md`](guides/writing-specs.md) — what goes in a spec,
  and when to skip it
- [`guides/writing-tasks.md`](guides/writing-tasks.md) — task granularity,
  types, body sections
- [`guides/smoke-test.sh`](guides/smoke-test.sh) — stands a board up in a
  throwaway repository and exercises every script that writes. Run it after
  touching `scripts/` or `templates/`; `install.sh` leaves it out

## Related

[research-log](https://github.com/norsage/research-log) records what the work
established (hypotheses, experiments, findings, protocols, decisions) while
this skill tracks the work itself. They share a `docs/` directory and nothing
else; either works without the other.
