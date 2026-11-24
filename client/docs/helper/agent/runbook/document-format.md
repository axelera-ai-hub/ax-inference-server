# Document Format

This runbook is split into topic files (see [index.md](index.md)), each a
self-contained workflow with its own intro and its own `##`-numbered
sub-sections starting at 1. Every topic file's title is a top-level (`#`)
section.

Within a top-level section, each `##` sub-section is one logical stage of
the workflow, and its title alone must say what it does (e.g. "Confirm
the target session", "Select a candidate device") — titles carry the
meaning, not prose. A sub-section that is a single action is written
directly under its `##` heading; a sub-section with multiple discrete
sub-actions breaks them into bold lettered sub-steps, `**Na. Title** —`
(where `N` is the sub-section number), each with its own equally
self-descriptive title.

The body of a `##` sub-section or lettered sub-step holds only its API
calls (call/response pairs) — never a free-standing explanatory
paragraph. The one allowed exception is a short clause riding on a
specific call, in the same line or sentence as that call: either a
parenthetical, non-bold aside directly below a call/response pair noting
its side effect (e.g. "(opens a confirmation dialog with ...)"), or a
trailing clause on that call describing what to do with, or how to read,
its result (e.g. "record the current max `id`", "poll ... until it reads
`"disabled":false`"). Anything broader than that — rationale, caveats,
or an explanation of branching/looping logic — belongs in `**Notes**:`
(below), never as its own paragraph inside the step body. A would-be
sub-step with no call of its own isn't given its own lettering; its
content goes straight into `**Notes**:` instead.

Every API call is one line: `` `METHOD /_agent/endpoint` `{"client_id",
"key":"value", ...}` `` — the bare `client_id` token means "pass the
session's client_id", not a literal value; other keys show the actual
value used. Its response follows on the next line: `` → `{"ok":true,
...}` `` — `{...}` elides nested or variable detail (`rect`, option
lists) that isn't essential to show in full. A `GET` call that takes no
body instead shows its query params inline as `` `GET /_agent/endpoint`
with `param=value`, ... ``.

Multiple calls belonging to one sub-step stack directly, with no blank
line between a response line and the next call line. A blank line
separates one lettered sub-step (or numbered sub-section) from the next.

Each sub-section ends with, in this order: one bold `**Verification**:`
paragraph — not one per sub-step — describing the authoritative check
that the sub-section's actions succeeded (screenshot, notification, or a
`/_agent/state` or `/_agent/graph` read); then, only when needed, one
bold `**Notes**:` paragraph — at the same level as `**Verification**:`,
never scattered between sub-steps — holding every free-text caveat,
rationale, or branching/looping explanation that would otherwise sit
inline in a step body. When a sub-section's notes cover more than one
lettered sub-step, list them as bullets prefixed by the sub-step (or
field) they apply to, e.g. "- **11b**: ...".

Plain numbered lists (`1.`, `2.`, ...) are used instead of lettered
sub-steps specifically where the logic branches or loops (e.g. a
retry-until-healthy device check), since lettering implies a fixed
linear sequence. A numbered list can either replace the lettered
sub-steps for an entire sub-section, or nest inside a single lettered
sub-step when only that one sub-step's logic branches or loops while the
rest of the sub-section stays linear (e.g. `**11c.** —`, whose loop is
introduced by nothing but its own title, with the branching logic itself
explained in `**Notes**:`). Inside such a list, a call and its response
may be folded into one inline sentence per numbered item (`` N.
<description>: `METHOD /_agent/endpoint` `{...}` → `{...}` ``) rather
than split across the usual two stacked lines, since the item's own
prose already carries the step label.

This document never narrates failed attempts, debugging, or the
discovery process — only the final, correct call shape and its actual
response.
