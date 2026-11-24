# Vision Demo: Single Pipeline

Runbook documenting the exact GUI `/_agent/*` FastAPI calls used to drive
the Pipeline Editor for this demo — endpoint, arguments, and how each step
is verified (screenshot vs. notification, and what it shows).

Host: a remote host, GUI `app.py` at `http://127.0.0.1:8080`, no `X-Agent-Key`
required.

---

## 1. Confirm the target session

`GET /_agent/sessions`
→ `{"sessions":[{"client_id":"<client_id>","has_socket_connection":true}]}`

**Verification**: response body itself — confirms `<client_id>` is
connected and is the only session.

## 2. Confirm the active tab

`GET /_agent/screenshot` with `client_id`, `max_width=1280`, `quality=0.5`
→ `{"ok":true,"image_base64":"...","format":"jpeg","width":1280,"height":629,"bytes":...}`

**Verification**: screenshot — decoded JPEG shows the **PIPELINE EDITOR**
tab active (bold/underlined in the top nav).

## 3. Force Stop All (button → confirm dialog → confirm)

**3a. Baseline notifications** — `GET /_agent/notifications` with
`since_id=0`, record the current max `id` so later notifications can be
isolated.

**3b. Highlight the button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"FORCE STOP ALL", "text":"Force stop all button"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**3c. Click it** — `POST /_agent/click` `{"client_id", "text":"FORCE STOP ALL"}`
→ `{"ok":true,"kind":"button","text":"dangerousForce Stop All"}`
(opens a confirmation dialog with `"Cancel"`/`"Force stop all"` buttons).

**3d. Highlight the dialog's confirm button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force stop all", "text":"Confirm force stop"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**3e. Click it** — `POST /_agent/click` `{"client_id", "text":"Force stop all"}`
→ `{"ok":true,"kind":"button","text":"Force stop all"}`

**3f. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` (no `id` → clears every highlight)
→ `{"ok":true}`

**Verification**: `GET /_agent/notifications` with `since_id=<baseline>`
→ two new notifications, both `"type":"info"`:
`"No axinferencenet_grpc processes were running"`,
`"No tracked vLLM/LLM servers were running"`. `type:"info"` (not
`"negative"`/error) is the GUI's affirmative, clean-state acknowledgement.
A follow-up poll at the new `since_id` returns an empty list, confirming
those two are final.

## 4. Clear the canvas (button → confirm prompt → Yes)

**4a. Highlight the clear-canvas icon** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete", "text":"Clear canvas button"}`
(icon ligature name `"delete"`)
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**4b. Click it** — `POST /_agent/click` `{"client_id", "text":"delete"}`
→ `{"ok":true,"kind":"button","text":"delete"}`
(opens a "Clear canvas?" confirm prompt with `"No"`/`"Yes"` buttons).

**4c. Highlight "Yes"** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Yes", "text":"Confirm clear canvas"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**4d. Click it** — `POST /_agent/click` `{"client_id", "text":"Yes"}`
→ `{"ok":true,"kind":"button","text":"Yes"}`

**4e. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: this action doesn't fire a `ui.notify()`, so
verification is a follow-up `GET /_agent/screenshot` — canvas is empty
(no nodes/edges) and no highlight boxes remain.

## 5. Build the pipeline: Input → Vision → Sink

**5a. Open "Sources"** —
`POST /_agent/highlight` `{"client_id", "kind":"text", "target":"Sources", "text":"Open Sources group"}`
→ `{"ok":true, ...}`
`POST /_agent/click` `{"client_id", "text":"Sources"}`
→ `{"ok":true,"kind":"tree-node", ...}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**5b. Add "Input"** —
`POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Input", "text":"Add Input node"}`
→ `{"ok":true,"kind":"palette","rect":{...}}`
`POST /_agent/add_node` `{"client_id", "label":"Input"}`
→ `{"ok":true,"node_id":"<node_id>","position":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**5c. Add "Vision"** (Models group already expanded) —
`POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Vision", "text":"Add Vision node"}`
→ `{"ok":true,"kind":"palette","rect":{...}}`
`POST /_agent/add_node` `{"client_id", "label":"Vision"}`
→ `{"ok":true,"node_id":"<node_id>","position":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**5d. Open "Sinks"** —
`POST /_agent/highlight` `{"client_id", "kind":"text", "target":"Sinks", "text":"Open Sinks group"}`
→ `{"ok":true, ...}`
`POST /_agent/click` `{"client_id", "text":"Sinks"}`
→ `{"ok":true,"kind":"tree-node", ...}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**5e. Add "Sink"** —
`POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Sink", "text":"Add Sink node"}`
→ `{"ok":true,"kind":"palette","rect":{...}}`
`POST /_agent/add_node` `{"client_id", "label":"Sink"}`
→ `{"ok":true,"node_id":"<node_id>","position":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/screenshot` — all three nodes (`Input`,
`Vision`, `Sink`) present on the canvas, palette tree shows
Sources/Models/Sinks all expanded with their leaves, no highlight boxes
remain.

## 6. Fit view (bring all nodes into frame)

**6a. Highlight the fit-view control** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"fit view", "text":"Fit view"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**6b. Click it** — `POST /_agent/click` `{"client_id", "text":"fit view"}`
→ `{"ok":true,"kind":"button","text":""}`
(matched by the Vue Flow control's `aria-label`, not a text/icon ligature.)

**6c. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/screenshot` — all three nodes (`Input`,
`Vision`, `Sink`) visible on the canvas, framed in view, no highlight
boxes remain.

## 7. Wire the pipeline: Input → Vision → Sink

**7a. Connect Input to Vision** — `POST /_agent/connect_nodes` `{"client_id", "source_id":"<Input node_id>", "target_id":"<Vision node_id>"}`
→ `{"ok":true,"source":"<Input node_id>","target":"<Vision node_id>"}`

**7b. Connect Vision to Sink** — `POST /_agent/connect_nodes` `{"client_id", "source_id":"<Vision node_id>", "target_id":"<Sink node_id>"}`
→ `{"ok":true,"source":"<Vision node_id>","target":"<Sink node_id>"}`

**Verification**: `GET /_agent/screenshot` — an edge runs from `Input`'s
right handle to `Vision`'s left handle, and another from `Vision`'s right
handle to `Sink`'s left handle.

## 8. Open the Input node's config dialog

**8a. Highlight the Input node** — `POST /_agent/highlight` `{"client_id", "kind":"node", "target":"<Input node_id>", "text":"Input node"}`
→ `{"ok":true,"id":"<anno-id>","kind":"node","rect":{...}}`

**8b. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**8c. Open it** — `POST /_agent/open_node` `{"client_id", "node_id":"<Input node_id>"}`
→ `{"ok":true,"node_id":"<Input node_id>"}`

**Verification**: `GET /_agent/screenshot` — an "Edit Input" dialog is
open over the canvas, showing the node's fields (Port, Interface,
Pipeline id, Timeout, Watchdog timeout, etc.).

## 9. Edit the Input node's fields and save

**9a. Set `imdecode_threads` to `16`** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"imdecode_threads", "text":"imdecode_threads"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"imdecode_threads", "value":"16"}`
→ `{"ok":true,"kind":"input"}`

**9b. Set `taskset_cpus` to `0-4`** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"taskset_cpus", "text":"taskset_cpus"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"taskset_cpus", "value":"0-4"}`
→ `{"ok":true,"kind":"input"}`

**9c. Set `membind` to `0`** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"membind", "text":"membind"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"membind", "value":"0"}`
→ `{"ok":true,"kind":"input"}`

**9d. Save** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/graph` — the Input node's `data` shows
`"imdecode_threads":16`, `"taskset_cpus":"0-4"`, `"membind":0`.

## 10. Open the Vision node's config dialog

**10a. Highlight the Vision node** — `POST /_agent/highlight` `{"client_id", "kind":"node", "target":"<Vision node_id>", "text":"Vision node"}`
→ `{"ok":true,"id":"<anno-id>","kind":"node","rect":{...}}`

**10b. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**10c. Open it** — `POST /_agent/open_node` `{"client_id", "node_id":"<Vision node_id>"}`
→ `{"ok":true,"node_id":"<Vision node_id>"}`

**Verification**: `GET /_agent/screenshot` — an "Edit Vision" dialog is
open over the canvas, showing the node's fields pre-filled (Network name,
Model `retinaface-mobilenet0.25-widerface-onnx`, device selector
`Device 0 (matis0:22:0) x 4/4 cores free`, Cores `4`, Output meta key
`face`, plus optional fields: labels file, meta key override, queue
depth `64`, queue timeout ms `2000`).

## 11. Configure the Vision node's model and device

**11a. Select the model** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model (.axnet, from host server)", "text":"Model dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"options":[{"text":"retinaface-mobilenet0.25-widerface-onnx","selected":true},{"text":"yolo26n-coco-onnx",...},...,{"text":"yolox-m-coco-onnx","selected":false}]}`
`POST /_agent/set_field` `{"client_id", "label":"Model (.axnet, from host server)", "value":"yolox-m-coco-onnx"}`
→ `{"ok":true,"kind":"select","text":"yolox-m-coco-onnx"}`

**11b. Run the device health-check** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Re-check device health", "text":"Re-check device health"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Re-check device health"}`
→ `{"ok":true,"kind":"button","text":"refreshRe-check device health"}`
Poll until it finishes: `GET /_agent/state` — the button
`{"text":"refreshRe-check device health", ...}` reads `"disabled":true`
while the check runs server-side; poll (e.g. every 2-3s) until it reads
`"disabled":false`.

**11c. Select a healthy device** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Devices (select one or more)", "text":"Devices dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Devices (select one or more)"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Devices (select one or more)"}`
→ `{"ok":true,"options":[{"text":"Device 0 (metis-0:22:0) -- 4/4 cores free  ⚠ FAILED HEALTH CHECK","selected":false},{"text":"Device 1 (metis-0:23:0) -- 4/4 cores free",...},...]}`
(pick any option whose text has no `"⚠ FAILED HEALTH CHECK"` suffix)
`POST /_agent/set_field` `{"client_id", "label":"Devices (select one or more)", "value":"Device 1 (metis-0:23:0) -- 4/4 cores free"}`
→ `{"ok":true,"kind":"select","text":"Device 1 (metis-0:23:0) -- 4/4 cores free"}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Devices (select one or more)"}`
→ `{"ok":true,"action":"closed","is_open":false}`

**11d. Set `meta_key_override` to `det`** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"meta_key_override", "text":"meta_key_override"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"meta_key_override", "value":"det"}`
→ `{"ok":true,"kind":"input"}`

**11e. Save** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/graph` — the Vision node's `data` shows
`"axnet"` resolved to the model selected in 11a (e.g.
`"${SDK_ROOT}/build/<model>/<model>.axnet"`), `"device"` set to the
device picked in 11c, and `"meta_key_override":"det"`.
`"meta_key_detected"` may not match — per the Output meta key field note
below, it reflects whichever model was selected when the dialog first
opened, not necessarily the one picked in 11a.

**Notes**:
- **11a**: a fresh SDK has no built vision models. The dialog then shows a free-text field
  `.axnet path (no vision models found…)` instead of the Model dropdown. Tick the
  **Use prebuilt models** checkbox. The field becomes the dropdown
  `Prebuilt model (axdownloadmodel catalog)`. Select the model there, for example
  `yolo26l-coco-onnx`. The GUI downloads and compiles it.
- **11b** (devices busy elsewhere): another GUI or a leftover vLLM server can hold devices. The
  health re-check may then miss a device that the compile step refuses later ("faulty device(s)
  detected"). Stop other GUI sessions and vLLM servers first. If the compile refuses a device,
  pick another device in 11c.
- **11b**: this button health-checks every device on the host in one
  pass — it is not scoped to whatever is currently selected in the
  Devices field. Its result (`GET /_agent/notifications`, a
  `{"type":"negative","message":"Unhealthy device(s): <indices>"}` entry
  whenever at least one device on the host is currently unhealthy, or
  `{"type":"positive","message":"All selected devices passed the health
  check"}` otherwise) only reports the host-wide picture; it is not a
  verdict on any one device you plan to pick. Do not branch on it
  directly — use it only to refresh the per-option annotations read in
  11c.
- **11c**: after 11b, every currently-unhealthy device's option text
  gains a `"  ⚠ FAILED HEALTH CHECK"` suffix (cleared again the next
  time 11b finds it healthy). Picking any option without that suffix is
  enough — no retry loop or notification branching is needed, since 11b
  already checked every device up front.
- **11c**: this is a multi-select — `set_field` toggles the named
  option, so calling it on an option that is already selected deselects
  it instead.
- **11b**: `/_agent/click` matches by visible label text with the
  button's icon ligature stripped out, so `"text"` here must be exactly
  `"Re-check device health"` (not `"refresh"`) — `"refresh"` alone is
  ambiguous with the meta-key-detect button next to the read-only
  "Output meta key" field (see below).
- **Output meta key field**: read-only — do not try to set it. It
  auto-populates from the compiled model's manifest, but only once, at
  the moment the dialog first opens, from whichever model was selected
  at that point. Switching the model afterward (11a) does not refresh
  it, and there is no reliable way to force a refresh: its refresh
  button is an icon-only control that shares the same bare "refresh"
  icon ligature as the device health-check button in 11b, so
  `/_agent/click` with `"text":"refresh"` is always ambiguous between the
  two — there is no unique label to click it by. Treat this field as
  informational only; do not read it to decide the meta key override.
- **11d**: for a detection model, the meta key override is always
  `"det"` — set it directly, independent of whatever the (possibly
  stale) Output meta key field above shows.

## 12. Generate and verify the Config YAML

**12a. Generate it** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Generate Config YAML", "text":"Generate Config YAML"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Generate Config YAML"}`
→ `{"ok":true,"kind":"button","text":"boltGenerate Config YAML"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
(opens a "Generate Config YAML" dialog with a "File name" field and a
read-only YAML preview field.)

**12b. Verify it** —
`GET /_agent/state` — read the dialog's YAML field value (the field with
`"label":null` and `"in_dialog":true`). Confirm it reflects every value
set in steps 9 and 11: `nets.<id>.axnet`, `axnet_config` (device and
cores), `meta_key_override`, and the pipeline's `taskset_cpus`,
`membind`, `imdecode_threads`. This is a live DOM read of the dialog's
rendered field, not a file on the host's disk — no SSH/file read involved.

**12c. Save it** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save YAML"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/notifications` — one new `"type":"positive"`
entry: `"Wrote <workdir>/client/ui/gui/generated_configs/<file name>.yaml"`.
This confirms a real file was written on the host's filesystem, in addition
to the dialog's live preview.

## 13. Compile and Launch Pipeline

**13a. Baseline notifications** — `GET /_agent/notifications` with
`since_id=0` (or the last known id), record the current max `id`.

**13b. Click it** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Compile and Launch Pipeline", "text":"Compile and Launch Pipeline button"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Compile and Launch Pipeline"}`
→ `{"ok":true,"kind":"button","text":"buildCompile and Launch Pipeline"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**13c. Poll until it finishes** — `GET /_agent/state` — the button's
`"disabled"` reads `true` while compiling/launching runs server-side;
poll (e.g. every 5s) until it reads `"disabled":false`.

**Verification**: `GET /_agent/notifications` with the baseline
`since_id` — two new `"type":"positive"` entries:
`"Compiled N pipeline spec(s) and sent to the host server:\n<pipeline
id> (port <port>): <path to pipeline_0.json>"`, then `"Launched N
pipeline(s)"`.

### If compiling fails with an OpenCL error

A model-provisioning smoke test runs as part of this step, with
`--enable-opencl` passed to `inference.py` whenever the global OpenCL
toggle is on. On a host whose platform doesn't support OpenCL, that
smoke test aborts with an error such as:

```
OpenCL not functional: Failed to get platform count! Error: Unknown OpenCL error
```

surfaced via a `"type":"negative"` notification: `"Cannot compile --
model provisioning failed: ... axnet.py regenerate/smoke-test failed for
model '<model>' on device <n>: ... died with <Signals.SIGABRT: 6>. ...
OpenCL not functional ..."`. This is independent of which device passed
the health check in 11c — it reproduces on any device when the
underlying platform lacks OpenCL support.

**Fix: disable OpenCL globally, then regenerate and retry** —

1. `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"OpenCL", "text":"OpenCL global toggle"}`
   → `{"ok":true,"kind":"toggle","rect":{...}}`
   `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
   `POST /_agent/set_field` `{"client_id", "label":"OpenCL", "value":"false"}`
   → `{"ok":true,"kind":"toggle","changed":true}`
2. Verify: `GET /_agent/state` — the `"OpenCL"` toggle's `"checked"` reads
   `false`.
3. Repeat 12a-12c (Generate Config YAML, verify, Save) — the regenerated
   YAML's `global.use_axinference_net_opencl` now reads
   `--disable-opencl` (was `--enable-opencl`). Verify this in 12b before
   saving.
4. Repeat 13a-13c (Compile and Launch Pipeline) — the model-provisioning
   smoke test no longer passes `--enable-opencl`, so it no longer hits
   this failure.
