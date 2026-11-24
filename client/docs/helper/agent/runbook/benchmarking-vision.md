# Benchmarking Vision Pipelines

A separate workflow from the [Vision Demo](vision-demo.md): benchmarking a pipeline
that is already compiled and launched (e.g. by completing steps 1-13
of that file first). Runbook documenting the exact GUI `/_agent/*` FastAPI calls
used to drive the Benchmarking tab.

## 1. Switch to the Benchmarking tab

`POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Benchmarking", "text":"Benchmarking tab"}`
→ `{"ok":true,"kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Benchmarking"}`
→ `{"ok":true,"kind":"tab","text":"Benchmarking"}`

## 2. Open the "Advanced Settings" right drawer

`POST /_agent/hover` `{"client_id", "text":"benchmark settings edge", "action":"enter"}`
→ `{"ok":true,"text":""}`

**Verification**: `GET /_agent/state` — `"drawer"` reads
`{"open":true,"rect":{...}}`.

**Notes**: the drawer has no clickable control of its own — it opens
only on mouse hover over a thin edge-sensor strip at the right screen
edge (`aria-label="benchmark settings edge"`), and closes the same way,
via a `mouseleave` on the drawer.

## 3. Confirm the pipeline is initialized

`GET /_agent/state` — the drawer's `"Inference endpoint(s)"` and
`"Pipeline ID(s) for backpressure monitoring"` fields.
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Inference endpoint(s)", "text":"Pipeline successfully initialized"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Pipeline ID(s) for backpressure monitoring", "text":"Pipeline successfully initialized"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: both fields read non-blank (e.g.
`"172.17.0.4:50060"` / `"model_vision_8"`) — this confirms the earlier
Compile and Launch Pipeline step (Vision Demo, step 13) succeeded, since
they auto-fill from the port(s) and pipeline id of whichever pipeline was
just compiled and launched.

## 4. Configure the live stat-series toggles

1. Per-source latency → off: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Per-source latency", "text":"Per-source latency"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `true`, `POST /_agent/set_field` `{"client_id", "label":"Per-source latency", "value":"false"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
2. CPU utilization → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"CPU utilization", "text":"CPU utilization"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"CPU utilization", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
3. Memory utilization → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Memory utilization", "text":"Memory utilization"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Memory utilization", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
4. Aggregate core utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate core utilization %", "text":"Aggregate core utilization %"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Aggregate core utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
5. Aggregate MVM utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate MVM utilization %", "text":"Aggregate MVM utilization %"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Aggregate MVM utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
6. Aggregate DDR utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate DDR utilization %", "text":"Aggregate DDR utilization %"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Aggregate DDR utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
7. Close the drawer: `POST /_agent/hover` `{"client_id", "text":"benchmark settings drawer", "action":"leave"}` → `{"ok":true,"text":"Advanced Settings..."}`

**Verification**: `GET /_agent/state` — `"drawer"` reads `{"open":false,...}`,
and the six toggles above read `checked:false/true/true/true/true/true`
respectively, matching their targets.

**Notes**: each item only calls `set_field` when the toggle's current
`checked` value doesn't already match its target — left alone otherwise.
`/_agent/hover`'s `leave` action requires a real matchable target for the
drawer itself (`aria-label="benchmark settings drawer"`, added to
`benchmark_settings_drawer` in `app.py` for this purpose) — the drawer's
mouseleave handler isn't reachable through the edge-sensor strip
(`"benchmark settings edge"`), which only has a `mouseenter` listener, and
`/_agent/click` never triggers it either, since it dispatches a synthetic
click directly on the matched element rather than moving a simulated
cursor across the page.

## 5. Add a file source

**5a. Open the dialog** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add file", "text":"Add file"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Add file"}`
→ `{"ok":true,"kind":"button","text":"add_photo_alternateAdd file"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
(opens an "Add file source" dialog with a "File / folder" dropdown,
"Count" and "FPS" fields, and "Cancel"/"Open" buttons.)

**5b. Select the file** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"File / folder dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"options":[...,{"text":"dancing_frame_t15_480p.jpg","selected":false},...]}`
`POST /_agent/set_field` `{"client_id", "label":"File / folder", "value":"dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"kind":"select","text":"dancing_frame_t15_480p.jpg"}`
(selecting an option in this single-select closes its own popup
automatically — no separate `toggle_dropdown` close call is needed.)

**5c. Set the sample count** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Count", "text":"Count field"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Count", "value":"5"}`
→ `{"ok":true,"kind":"input"}`
("FPS" is left at its default.)

**5d. Open it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Open", "text":"Open"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Open"}`
→ `{"ok":true,"kind":"button","text":"Open"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/state` — `"sources"` holds 5 entries
(`src-N`), each `"status":"live"`, `"has_frame":true`, non-zero
`"capture_fps"`/`"infer_fps"`, a real `"latency_ms"`, and `"det_count"` > 0.

**Notes**: the `"File / folder"` dropdown's option text comes from the
host's media directory listing (`/_agent/read_dropdown_options`) — use
the exact listed filename, not a spoken/transcribed approximation of it.

## 6. Clear the Plotly plot and let it refill

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"plot refresh", "text":"Clear plot"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"plot refresh"}`
→ `{"ok":true,"kind":"button","text":"refresh"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
(wait ~30s afterward for the cleared plot to refill with new samples
before continuing to the next step.)

**Verification**: the Plotly plot visibly resets and begins
re-accumulating points from empty.

**Notes**: the page has two buttons sharing the same `refresh` icon
ligature (this one and the chat panel's own refresh button) — match on
its `aria-label`, `"plot refresh"` (set via `.props('...
aria-label="plot refresh"')` in `app.py`), not the bare icon name, or
`/_agent/highlight`/`/_agent/click` return
`{"ok":false,"error":"ambiguous","matched_count":2}`.

## 7. Remove all sources

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete_sweep", "text":"Remove all sources"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"delete_sweep"}`
→ `{"ok":true,"kind":"button","text":"delete_sweep"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/notifications` — one new `"type":"positive"`
entry, `"removed N source(s)"`. A follow-up `GET /_agent/state` —
`"sources"` reads `{}`.

## 8. Switch to the Pipeline Editor tab

`POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Pipeline Editor", "text":"Pipeline Editor tab"}`
→ `{"ok":true,"kind":"tab","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Pipeline Editor"}`
→ `{"ok":true,"kind":"tab","text":"Pipeline Editor"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/state` — `"tabs"` reads
`[{"text":"Pipeline Editor","active":true},{"text":"Benchmarking","active":false}]`.

## 9. Force Stop All (button → confirm dialog → confirm)

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force Stop All", "text":"Force Stop All"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Force Stop All"}`
→ `{"ok":true,"kind":"button","text":"dangerousForce Stop All"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
(opens a confirmation dialog with `"Cancel"`/`"Force stop all"` buttons.)
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force stop all", "text":"Confirm Force Stop All"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Force stop all"}`
→ `{"ok":true,"kind":"button","text":"Force stop all"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/notifications` — two new entries:
`"type":"positive"` `"Force-stopped N pipeline process(es): <pid>"`, then
`"type":"info"` `"No tracked vLLM/LLM servers were running"`.

## 10. Clear the canvas (button → confirm prompt → Yes)

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete", "text":"Clear canvas button"}`
(icon ligature name `"delete"`)
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"delete"}`
→ `{"ok":true,"kind":"button","text":"delete"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
(opens a "Clear canvas?" confirm prompt with `"No"`/`"Yes"` buttons.)
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Yes", "text":"Confirm clear canvas"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Yes"}`
→ `{"ok":true,"kind":"button","text":"Yes"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/graph` → `{"nodes":[],"edges":[]}`.

**Notes**: this confirm prompt is a custom overlay, not a Quasar
`.q-dialog` — `/_agent/state`'s `"dialog_open"` field stays `false` the
entire time it's showing; read `/_agent/state`'s `"buttons"` list for its
`"No"`/`"Yes"` entries instead if confirmation it's open is needed before
clicking.
