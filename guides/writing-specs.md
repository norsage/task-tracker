# Writing specs

A spec is the document that exists *before* tasks. It captures enough
context that someone (you, a teammate, an agent) picking the work up
later understands what's being attempted and why.

It is the engineering analogue of a PRD, written in plain terms rather
than product ones: no "success criteria", no "user stories", no
"business value".

## When to write one

Write a spec when the work:

- spans more than one or two tasks
- has unresolved questions about *what* or *how*, beyond *do this*
- will produce results others should be able to reproduce or audit

Skip the spec when the work is small, mechanical, or self-explanatory
(e.g. "rename module X", "upgrade dep Y"). A task with a clear title is
enough.

## Sections

### Context

What's the situation we're operating in? What's already been tried, what
prompted this work, what does the reader need to know to evaluate the
rest of the spec? Link prior tasks, specs, papers, repos.

Keep it factual. Save opinions for *Approach*.

### Question / Goal

A single paragraph, phrased as an outcome: "End-to-end pipeline from raw
logs to evaluation report, runnable from a single command."

If you can't write this in one paragraph, the spec is probably trying to
do two things. Split it.

### Approach

How we plan to attack it. Methods, the architecture you have in mind.
*List alternatives you considered and why this one*; the rejected paths
are what you go back to when the work surprises you.

### Out of scope

Things this spec is explicitly not doing. Reviewers calibrate against
this; future-you avoids scope creep against it.

### Risks & unknowns

What could make this not work, what assumptions we'd have to revisit if
they break, data we don't yet have. Anything that would cause us to
abandon or pivot.

### Evaluation

How will we know we are making progress? Which behaviours we expect to
verify, and what "working" looks like, described as signals rather than
as a binary gate.

### References

Papers, prior work, related specs, external tickets, repos.

## After writing

When the spec is reasonable, set `status: active` and generate tasks
from it. Each task should link back with `spec: <id>`. The spec itself
gets revisited as the work turns up surprises: bump `updated`, edit in
place.

When the work concludes, set `status: archived` and let `archive.py`
sweep it after the digest period.
