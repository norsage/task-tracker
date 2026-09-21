---
# Board settings. Copy to <board root>/.task-tracker.md, next to tasks/ and
# specs/, not inside them. Every key is optional; the values below are the
# defaults.

# Characters of random discriminator appended to each id: 0042.k3f
#
# This is a wire format, not a preference. Commit it, and keep it the same
# for every writer on this board. The number in an id is allocated locally as
# max+1, so two branches forked from one commit both mint 0042; the suffix is
# what keeps them apart. Sizing, as P(collision) for k branches contesting one
# number, and board-wide for k branches creating n tasks each:
#
#   width   k=2      k=3      k=10     k=10, n=10
#   2       0.098%   0.29%    4.3%     36%
#   3       0.003%   0.009%   0.14%    1.4%
#   4       0.0001%  0.0003%  0.004%   0.04%
#
# 0 disables suffixes entirely. Only safe on a genuinely single-writer board,
# and note that solo is not single-writer: worktrees, a second machine, or a
# swarm of agents under one git identity are all concurrent writers. Mixing 0
# with a nonzero width across writers is the one unsafe combination: a bare
# `0042` is then both a valid id and a prefix of `0042.k3f`.
#
# Raising it later is free: ids are allocated max+1, so numbers never overlap
# across time and old bare ids coexist with new suffixed ones.
suffix_length: 3

# Zero-padding of the number part.
id_width: 4

# archive.py moves terminal items older than this. --older-than-days wins.
archive_after_days: 14
---

# Task tracker board settings

The frontmatter above configures this board. The body is yours. It is a good
place for the conventions that belong to this board and not to the tool.
