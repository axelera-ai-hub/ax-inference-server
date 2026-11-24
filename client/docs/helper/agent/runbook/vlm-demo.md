# VLM Demo

Runbook documenting the exact GUI `/_agent/*` FastAPI calls used to drive
the Pipeline Editor for a video language model demo — endpoint,
arguments, and how each step is verified.

Host: a remote host, GUI `app.py` at `http://127.0.0.1:8080`, no `X-Agent-Key`
required.

---

## 1. Confirm the target session

`GET /_agent/sessions`
→ `{"sessions":[{"client_id":"<client_id>","has_socket_connection":true}]}`

**Verification**: response body itself — confirms `<client_id>` is
connected and is the only session.

## 2. Confirm the active tab

`GET /_agent/state` with `client_id`
→ `{"tabs":[{"text":"Pipeline Editor","active":true},{"text":"Benchmarking","active":false}], ...}`

**Verification**: response body itself — `"Pipeline Editor"` reads
`"active":true`.

## 3. Force Stop All (button → confirm dialog → confirm)

**3a. Highlight the button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force Stop All", "text":"Force stop all button"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**3b. Click it** — `POST /_agent/click` `{"client_id", "text":"Force Stop All"}`
→ `{"ok":true,"kind":"button","text":"dangerousForce Stop All"}`
(opens a confirmation dialog with `"Cancel"`/`"Force stop all"` buttons.)

**3c. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**3d. Highlight the dialog's confirm button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force stop all", "text":"Confirm force stop"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**3e. Click it** — `POST /_agent/click` `{"client_id", "text":"Force stop all"}`
→ `{"ok":true,"kind":"button","text":"Force stop all"}`

**3f. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/notifications` with `since_id=<baseline>`
→ two new notifications, both `"type":"info"`:
`"No axinferencenet_grpc processes were running"`,
`"No tracked vLLM/LLM servers were running"`.

## 4. Clear the canvas (button → confirm prompt → Yes)

**4a. Highlight the clear-canvas icon** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete", "text":"Clear canvas button"}`
(icon ligature name `"delete"`)
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**4b. Click it** — `POST /_agent/click` `{"client_id", "text":"delete"}`
→ `{"ok":true,"kind":"button","text":"delete"}`
(opens a "Clear canvas?" confirm prompt with `"No"`/`"Yes"` buttons.)

**4c. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**4d. Highlight "Yes"** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Yes", "text":"Confirm clear canvas"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**4e. Click it** — `POST /_agent/click` `{"client_id", "text":"Yes"}`
→ `{"ok":true,"kind":"button","text":"Yes"}`

**4f. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/graph` with `client_id`
→ `{"nodes":[],"edges":[]}` — canvas is genuinely empty.

**Notes**: the "Clear canvas?" confirm prompt is a custom overlay, not a
Quasar dialog, so `/_agent/state`'s `"dialog_open"` field stays `false`
while it is showing — check the `"buttons"` list for `"No"`/`"Yes"`
instead.

## 5. Build the pipeline: Input → (V/L)LM → Sink

**5a. Add "Input"** —
`POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Input", "text":"Add Input node"}`
→ `{"ok":true,"kind":"palette","rect":{...}}`
`POST /_agent/add_node` `{"client_id", "label":"Input"}`
→ `{"ok":true,"node_id":"<Input node_id>","position":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**5b. Add "(V/L)LM"** (Models group) —
`POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"(V/L)LM", "text":"Add (V/L)LM node"}`
→ `{"ok":true,"kind":"palette","rect":{...}}`
`POST /_agent/add_node` `{"client_id", "label":"(V/L)LM"}`
→ `{"ok":true,"node_id":"<(V/L)LM node_id>","position":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**5c. Add "Sink"** —
`POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Sink", "text":"Add Sink node"}`
→ `{"ok":true,"kind":"palette","rect":{...}}`
`POST /_agent/add_node` `{"client_id", "label":"Sink"}`
→ `{"ok":true,"node_id":"<Sink node_id>","position":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/graph` with `client_id` — all three nodes
(`Input`, `(V/L)LM`, `Sink`) present, each with its own `data.kind`
(`input`, `vllm_vlm`, `sink`).

**Notes**: the palette's leaf for this demo is labeled `"(V/L)LM"`, not
`"VLM"` — the same vLLM/axplugin-backed node and dialog (`kind:
"vllm_vlm"`) drives either a text-only LLM or a VLM via its `is_vlm`
field, depending on the model configured.

## 6. Fit view (bring all nodes into frame)

**6a. Highlight the fit-view control** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"fit view", "text":"Fit view"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**6b. Click it** — `POST /_agent/click` `{"client_id", "text":"fit view"}`
→ `{"ok":true,"kind":"button","text":""}`
(matched by the Vue Flow control's `aria-label`, not a text/icon ligature.)

**6c. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/screenshot` — all three nodes (`Input`,
`(V/L)LM`, `Sink`) visible on the canvas, framed in view, no highlight
boxes remain.

## 7. Wire the pipeline: Input → (V/L)LM → Sink

**7a. Connect Input to (V/L)LM** — `POST /_agent/connect_nodes` `{"client_id", "source_id":"<Input node_id>", "target_id":"<(V/L)LM node_id>"}`
→ `{"ok":true,"source":"<Input node_id>","target":"<(V/L)LM node_id>"}`

**7b. Connect (V/L)LM to Sink** — `POST /_agent/connect_nodes` `{"client_id", "source_id":"<(V/L)LM node_id>", "target_id":"<Sink node_id>"}`
→ `{"ok":true,"source":"<(V/L)LM node_id>","target":"<Sink node_id>"}`

**Verification**: `GET /_agent/graph` with `client_id` — `"edges"` holds
exactly two entries, `Input → (V/L)LM` and `(V/L)LM → Sink`.

## 8. Open the (V/L)LM node's config dialog

**8a. Highlight the (V/L)LM node** — `POST /_agent/highlight` `{"client_id", "kind":"node", "target":"<(V/L)LM node_id>", "text":"(V/L)LM node"}`
→ `{"ok":true,"id":"<anno-id>","kind":"node","rect":{...}}`

**8b. Clear all highlights** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**8c. Open it** — `POST /_agent/open_node` `{"client_id", "node_id":"<(V/L)LM node_id>"}`
→ `{"ok":true,"node_id":"<(V/L)LM node_id>"}`

**Verification**: `GET /_agent/state` with `client_id` — `"dialog_open":true`,
and the dialog's `"fields"` show `"Artifact (from host server)"`,
`"Device(s) -- one vLLM server launches per device selected"`, `"Port
(base port -- +1 per additional device)"`, `"temperature"`, `"Image
resize width (px)"`, `"Image resize height (px)"`, plus toggles
`"enable_thinking"` and `"Is VLM (image input)"`.

## 9. Configure the (V/L)LM node's artifact and device

**9a. Select the artifact** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Artifact (from host server)", "text":"Artifact dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Artifact (from host server)"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Artifact (from host server)"}`
→ `{"ok":true,"options":[{"text":"smolvlm2-256m-video-instruct","selected":true}]}`
`POST /_agent/set_field` `{"client_id", "label":"Artifact (from host server)", "value":"smolvlm2-256m-video-instruct"}`
→ `{"ok":true,"kind":"select","text":"smolvlm2-256m-video-instruct"}`

**9b. Run the device health-check** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"refresh", "text":"Device health-check button"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"refresh"}`
→ `{"ok":true,"kind":"button","text":"refresh"}`
Poll until it finishes: `GET /_agent/state` with `client_id` — the
in-dialog button whose `"icon"` is `"refresh"` reads `"disabled":true`
while the check runs server-side; poll (e.g. every 2-3s) until it reads
`"disabled":false`.

**9c. Select a healthy device** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Device(s) -- one vLLM server launches per device selected", "text":"Devices dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Device(s) -- one vLLM server launches per device selected"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Device(s) -- one vLLM server launches per device selected"}`
→ `{"ok":true,"options":[{"text":"metis-0:22:0 (device 0)  ⚠ FAILED HEALTH CHECK","selected":false},{"text":"metis-0:23:0 (device 1)","selected":false},...]}`
(pick any option whose text has no `"⚠ FAILED HEALTH CHECK"` suffix)
`POST /_agent/set_field` `{"client_id", "label":"Device(s) -- one vLLM server launches per device selected", "value":"metis-0:23:0 (device 1)"}`
→ `{"ok":true,"kind":"select","text":"metis-0:23:0 (device 1)"}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Device(s) -- one vLLM server launches per device selected"}`
→ `{"ok":true,"action":"closed","is_open":false}`

**Verification**: `GET /_agent/graph` with `client_id` — the `(V/L)LM`
node's `data` shows `"artifact"` resolved to
`"${SDK_ROOT}/build/smolvlm2-256m-video-instruct/axscript"` and
`"devices"` holding exactly the device name picked in 9c (e.g.
`["metis-0:23:0"]`).

**Notes**:
- **9b**: this button health-checks every device on the host in one pass
  — it is not scoped to whatever is currently selected in the Devices
  field. Its result (`GET /_agent/notifications`, a
  `{"type":"negative","message":"Unhealthy device(s): <device
  names>"}` entry whenever at least one device on the host is currently
  unhealthy, or `{"type":"positive","message":"All selected devices
  passed the health check"}` when none are, or when a device was already
  selected and happens to be in the healthy set) only reports the
  host-wide picture; it is not a verdict on any one device you plan to
  pick. Do not branch on it directly — use it only to refresh the
  per-option annotations read in 9c.
- **9c**: after 9b, every currently-unhealthy device's option text gains
  a `"  ⚠ FAILED HEALTH CHECK"` suffix (cleared again the next time 9b
  finds it healthy). Picking any option without that suffix is enough —
  no retry loop or notification branching is needed, since 9b already
  checked every device up front.
- **9c**: this node's device field renders each option and its own
  current value as `"<device name> (device <index>)"` (e.g. `"metis-0:23:0
  (device 1)"`), not Vision's `"Device <index> (<device name>) -- <cores>
  cores free"` format — there is no per-device core count for this node.
- **9c**: this is a multi-select — `set_field` toggles the named option,
  so calling it on an option that is already selected deselects it
  instead.
- **9b**: unlike the Vision node, this dialog has only one icon-only
  `"refresh"` control, so `/_agent/click`/`/_agent/highlight` with
  `"text":"refresh"` is unambiguous here — there is no second
  meta-key-detect button to collide with.

## 10. Configure the (V/L)LM node's generation settings and save

**10a. Enable thinking mode** —
`POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"enable_thinking", "text":"enable_thinking toggle"}`
→ `{"ok":true,"kind":"toggle","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"enable_thinking", "value":"true"}`
→ `{"ok":true,"kind":"toggle","changed":true}`

**10b. Enable "Is VLM (image input)"** —
`POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Is VLM (image input)", "text":"Is VLM toggle"}`
→ `{"ok":true,"kind":"toggle","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Is VLM (image input)", "value":"true"}`
→ `{"ok":true,"kind":"toggle","changed":true}`

**10c. Set image resize width to 256** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Image resize width (px)", "text":"Image resize width"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Image resize width (px)", "value":"256"}`
→ `{"ok":true,"kind":"input"}`

**10d. Set image resize height to 256** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Image resize height (px)", "text":"Image resize height"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Image resize height (px)", "value":"256"}`
→ `{"ok":true,"kind":"input"}`

**10e. Save** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/graph` with `client_id` — the `(V/L)LM`
node's `data` shows `"port":8001`, `"enable_thinking":true,
"temperature":0, "is_vlm":true, "resize_width":256, "resize_height":256`,
alongside the `"artifact"` and `"devices"` set in section 9.

**Notes**: port and temperature are left at their defaults (`8001` and
`0`) here, matching the requested config, so no `set_field` call is
needed for either.

## 11. Compile and Launch Pipeline

**11a. Baseline notifications** — `GET /_agent/notifications` with
`client_id` and `since_id=0` (or the last known id), record the current
max `id`.

**11b. Click it** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Compile and Launch Pipeline", "text":"Compile and Launch Pipeline button"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Compile and Launch Pipeline"}`
→ `{"ok":true,"kind":"button","text":"buildCompile and Launch Pipeline"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**11c. Poll until it finishes** — `GET /_agent/notifications` with
`client_id` and the baseline `since_id`; poll (e.g. every 3s) until a new
entry appears.

**Verification**: `GET /_agent/notifications` with the baseline
`since_id` — one new `"type":"positive"` entry: `"Launched 1 vLLM VLM
server(s): <(V/L)LM node_id> (port 8001)"`.
