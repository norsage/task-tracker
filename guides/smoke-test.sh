#!/usr/bin/env bash
# Stand a board up in a throwaway repository and exercise every script that
# writes. Run it after touching scripts/ or templates/; it takes a second and
# needs nothing but git and python3.
#
#   bash guides/smoke-test.sh
#
# A development document: install.sh does not copy it.

set -euo pipefail

TT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$WORK"
git init -q .
git config user.email smoke@test
git config user.name "Smoke Test"
echo x > code.py
git add -A
git commit -qm init

run() { python3 "$TT/scripts/$1.py" "${@:2}"; }

# A spec, an epic under it, and two tasks — one blocked on the other.
SPEC=$(run new spec "Baseline comparison" --description "Does X beat Y" | grep -oE '[0-9]{4}\.[a-z0-9]+')
EPIC=$(run new epic "Training runs" --spec "$SPEC" | grep -oE '[0-9]{4}\.[a-z0-9]+')
T1=$(run new task "Prepare the dataset" --spec "$SPEC" --epic "$EPIC" \
        --priority high --effort M --tags data | grep -oE '[0-9]{4}\.[a-z0-9]+')
T2=$(run new task "Train the baseline" --spec "$SPEC" --epic "$EPIC" \
        --depends-on "$T1" --exits docs/findings/ | grep -oE '[0-9]{4}\.[a-z0-9]+')

# Both were filed as ideas; the board only hands out planned work.
for f in docs/tasks/*.md; do
    python3 - "$f" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
open(p, "w").write(re.sub(r"^status: idea$", "status: planned", s, count=1, flags=re.M))
PY
done

# T2 depends on T1, so the claim must land on T1 and nothing else.
CLAIMED=$(run next --claim --type task --json | grep -oE '[0-9]{4}\.[a-z0-9]+' | head -1)
[ "$CLAIMED" = "$T1" ] || { echo "claim picked $CLAIMED, expected $T1" >&2; exit 1; }
run next --claim --type task >/dev/null 2>&1 && {
    echo "second claim should have found nothing: $T2 depends on $T1" >&2; exit 1; }

# An evidence trail appears, so the task changes shape.
run promote "$T1" --dry-run >/dev/null
run promote "$T1" >/dev/null
README=$(find docs/tasks -name README.md)
[ -f "$README" ] || { echo "promote left no README.md" >&2; exit 1; }
grep -q "^id: $T1$" "$README" || { echo "promoted the wrong task" >&2; exit 1; }

run index
run index --check
run refs --check

# Close T1 and archive it; the digest outlives the file.
python3 - "$README" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
open(p, "w").write(re.sub(r"^status: in-progress$", "status: done", s, count=1, flags=re.M))
PY

run archive --older-than-days 0 --dry-run >/dev/null
run archive --older-than-days 0
ls docs/tasks/archive/*/ >/dev/null
ls docs/tasks/archive/digest-*.md >/dev/null

run index
run refs --check

echo "smoke test passed"
