# Examples: Two-Stage Cascade

Runbook for the palette's **Examples** group: opening the pre-built
**Two-Stage Cascade** wizard (Primary model → Filter → Secondary model,
cropped per detection) instead of building the pipeline node by node. The
primary (detection) and secondary (pose) models are deployed on the same
device, sharing its cores. Same host and conventions as the other topics.

## 1. Confirm the target session

`GET /_agent/sessions`
→ `{"sessions":[{"client_id":"<client_id>","has_socket_connection":true}]}`

**Verification**: response body itself — confirms `<client_id>` is connected and is the only session.

**Notes**: if a later call returns `{"detail":"no connected client with id '<client_id>'"}`, the browser page reconnected under a new `client_id`; repeat this sub-section and redo the interrupted step.

## 2. Force Stop All (button → confirm dialog → confirm)

**2a. Baseline notifications** — `GET /_agent/notifications` with `since_id=0`, record the current max `id`.

**2b. Click the button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"FORCE STOP ALL", "text":"Force stop all button"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"FORCE STOP ALL"}`
→ `{"ok":true,"kind":"button","text":"dangerousForce Stop All"}`
(opens a confirmation dialog with `"Cancel"`/`"Force stop all"` buttons).

**2c. Confirm** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force stop all", "text":"Confirm force stop"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Force stop all"}`
→ `{"ok":true,"kind":"button","text":"Force stop all"}`

**Verification**: `GET /_agent/notifications` with `since_id=<baseline>` → two new `"type":"info"` notifications: `"No axinferencenet_grpc processes were running"`, `"No tracked vLLM/LLM servers were running"`.

**Notes**: that is the idle-host result. If pipelines are still running from an earlier launch, the first notification is instead `"type":"positive"` `"Force-stopped N pipeline process(es): <pid>, ..."` (N = the number of launched pipelines), followed by the same vLLM/LLM info notification; it can take several seconds to appear.

## 3. Clear the canvas (button → confirm prompt → Yes)

**3a. Click the clear-canvas icon** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete", "text":"Clear canvas button"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"delete"}`
→ `{"ok":true,"kind":"button","text":"delete"}`
(opens a "Clear canvas?" confirm prompt with `"No"`/`"Yes"` buttons).

**3b. Confirm** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Yes", "text":"Confirm clear canvas"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Yes"}`
→ `{"ok":true,"kind":"button","text":"Yes"}`

**Verification**: `GET /_agent/graph` → `{"nodes":[],"edges":[]}`.

**Notes**: the confirm prompt is a custom overlay, so `/_agent/state`'s `"dialog_open"` stays `false` while it shows.

## 4. Open the Two-Stage Cascade wizard

**4a. Expand the "Examples" group** — `POST /_agent/highlight` `{"client_id", "kind":"text", "target":"Examples", "text":"Open Examples group"}`
→ `{"ok":true,"id":"<anno-id>","kind":"text","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Examples"}`
→ `{"ok":true,"kind":"tree-node","text":"play_arrowExamples"}`

**4b. Open the wizard** — `POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Two-Stage Cascade", "text":"Click Two-Stage Cascade"}`
→ `{"ok":true,"id":"<anno-id>","kind":"palette","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Two-Stage Cascade"}`
→ `{"ok":true,"kind":"tree-node","text":"scienceTwo-Stage Cascade"}`

**Verification**: `GET /_agent/state` → `"dialog_open":true`; the dialog's buttons are `"Run Health Check (all models)"`, `"Cancel"`, `"Generate Pipeline"`; its fields are `"Model (.axnet, from host server)"`, `"Devices (select one or more)"`, `"Cores on Device <D> (<F>/4 free)"`, `"meta_key_override (optional -- set this if this model's defa"`, `"classes (optional, comma-separated class indices to keep fro"`, `"imdecode_threads override (blank = auto, 4x pinned cores)"`, `"imdecode_queue_depth"`, `"imdecode_queue_timeout_ms"` and the `"Use prebuilt models (axdownloadmodel catalog instead of buil..."` toggle. `GET /_agent/graph` stays `{"nodes":[],"edges":[]}`.

**Notes**:
- **4b**: the Primary model radio is selected on open; `Devices` defaults to the first device (`Device 0`), `Cores` to all its free cores, and `Model` to the first catalog entry. The same fields are re-used for the Secondary model after switching the radio (§6), and each model keeps its own values.
- **4b**: the `Devices` options read `Device <D> (<bus id>) -- <F>/4 cores free`; pick a device with at least the cores needed for both models combined (here 1 + 3 = 4).

## 5. Configure the primary (detection) model

**5a. Open the dropdown** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model (.axnet, from host server)", "text":"Model dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"options":[{"text":"yolo26npose-coco-onnx","selected":false},...,{"text":"yolox-m-coco-onnx","selected":false}]}`

**5b. Pick "yolox-m-coco-onnx"** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model (.axnet, from host server)", "text":"Select yolox-m-coco-onnx"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Model (.axnet, from host server)", "value":"yolox-m-coco-onnx"}`
→ `{"ok":true,"kind":"select","text":"yolox-m-coco-onnx"}`

**5c. Choose the device** — the first free device is `Device <D>`, already selected by default; to change it, use the device-change steps in §8.

**5d. Set the primary model's cores** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Cores on Device <D> (<F>/4 free)", "text":"Primary cores = 1"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Cores on Device <D> (<F>/4 free)", "value":"1"}`
→ `{"ok":true,"kind":"input"}`

**5e. Set the meta key override** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"meta_key_override (optional -- set this if this model's defa", "text":"Meta key det"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"meta_key_override (optional -- set this if this model's defa", "value":"det"}`
→ `{"ok":true,"kind":"input"}`

**5f. Set the class filter** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"classes (optional, comma-separated class indices to keep fro", "text":"Keep class 0 (person)"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"classes (optional, comma-separated class indices to keep fro", "value":"0"}`
→ `{"ok":true,"kind":"input"}`

**5g. Set the decode threads** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"imdecode_threads override (blank = auto, 4x pinned cores)", "text":"imdecode threads 16"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"imdecode_threads override (blank = auto, 4x pinned cores)", "value":"16"}`
→ `{"ok":true,"kind":"input"}`

**Verification**: `GET /_agent/state` — the dialog's fields read `"Model (.axnet, from host server)"` `"yolox-m-coco-onnx"`, `"Cores on Device <D> (<F>/4 free)"` `"1"`, `"meta_key_override (optional -- set this if this model's defa"` `"det"`, `"classes (optional, comma-separated class indices to keep fro"` `"0"`, `"imdecode_threads override (blank = auto, 4x pinned cores)"` `"16"`.

**Notes**:
- **5a–5b**: `set_field` on the model closes the dropdown by itself.
- **5e**: the label contains an apostrophe; it is a JSON string, so pass it unmodified (when driving the call through a shell, send the body on stdin instead of inside single quotes).
- **5f**: the class filter sits under "Filter (primary model's detections, before cropping)" and applies to the primary model's detections; class `0` is person.

## 6. Configure the secondary (pose) model

**6a. Switch to the Secondary model** — `POST /_agent/highlight` `{"client_id", "kind":"pointer", "x":0.42, "y":0.2, "text":"Switch to Secondary model"}`
→ `{"ok":true,"id":"<anno-id>","kind":"pointer","point":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Secondary model"}`
→ `{"ok":true,"kind":"toggle","text":"Secondary model"}`

**6a. Open the dropdown** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model (.axnet, from host server)", "text":"Model dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"options":[{"text":"yolo26npose-coco-onnx","selected":false},...,{"text":"yolox-m-coco-onnx","selected":false}]}`

**6b. Pick "yolo26npose-coco-onnx"** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model (.axnet, from host server)", "text":"Select yolo26npose-coco-onnx"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Model (.axnet, from host server)", "value":"yolo26npose-coco-onnx"}`
→ `{"ok":true,"kind":"select","text":"yolo26npose-coco-onnx"}`

**6c. Choose the device** — the same device as the primary model (`Device <D>`).

**6d. Set the secondary model's cores** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Cores on Device <D> (<F>/4 free)", "text":"Secondary cores = 3"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Cores on Device <D> (<F>/4 free)", "value":"3"}`
→ `{"ok":true,"kind":"input"}`

**6e. Set the meta key override** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"meta_key_override (optional -- set this if this model's defa", "text":"Meta key pose"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"meta_key_override (optional -- set this if this model's defa", "value":"pose"}`
→ `{"ok":true,"kind":"input"}`

**Verification**: `GET /_agent/state` — the dialog's fields now read `"Model (.axnet, from host server)"` `"yolo26npose-coco-onnx"`, `"Cores on Device <D> (<F>/4 free)"` `"3"`, `"meta_key_override (optional -- set this if this model's defa"` `"pose"`; the class filter and decode threads keep the values set in §5.

**Notes**:
- **6a**: a text-matched highlight of `"Secondary model"` is `"ambiguous"` (the wizard's description line contains the same words), so the radio is highlighted with a `"pointer"` at its viewport position instead; the click on `"Secondary model"` itself is unambiguous. To return to the Primary model use the same two calls with `"Primary model"` and `"x":0.32`.
- **6c–6d**: the primary and secondary cores must add up to at most the device's cores (1 + 3 = 4).

## 7. Run the health check for all models

**7a. Baseline notifications** — `GET /_agent/notifications` with `since_id=0`, record the current max `id`.

**7b. Run it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Run Health Check (all models)", "text":"Run health check"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Run Health Check (all models)"}`
→ `{"ok":true,"kind":"button","text":"Run Health Check (all models)"}`
(takes about a minute; poll `GET /_agent/screenshot` until the result lines appear below the fields).

**Verification**: `GET /_agent/screenshot` with `client_id`, `max_width=1280`, `quality=0.6` — the bottom of the dialog reads, one line per model, `Primary model: <H> / <T> device(s) healthy (indices: <comma-separated healthy device indices>)` and `Secondary model: <H> / <T> device(s) healthy (indices: ...)`. The chosen device `<D>` must be in both index lists; if it is not, do §8. `GET /_agent/notifications` with `since_id=<baseline>` returns no new entries.

**Notes**: the result is shown only in the dialog, not as a notification, so it is read from the screenshot. The lists can differ per model.

## 8. Move both models to a healthy device (only when `<D>` is not in an index list)

Do this for each model that failed the check (switch the radio first, §6a), then re-set its cores, because changing the device resets them:

1. Open the dropdown: `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Devices (select one or more)", "text":"Devices dropdown"}` → `POST /_agent/clear_highlight` `{"client_id"}` → `POST /_agent/toggle_dropdown` `{"client_id", "label":"Devices (select one or more)"}` → `{"ok":true,"action":"opened","is_open":true}`
2. Add the healthy device (highlight, clear, then): `POST /_agent/set_field` `{"client_id", "label":"Devices (select one or more)", "value":"Device <D> (<bus id>) -- 4/4 cores free"}` → `{"ok":true,"kind":"select","text":"Device <D> (<bus id>) -- 4/4 cores free"}`
3. Remove the unhealthy device (highlight, clear, then): `POST /_agent/set_field` `{"client_id", "label":"Devices (select one or more)", "value":"Device <D0> (<bus id>) -- 4/4 cores free"}` → `{"ok":true,"kind":"select","text":"Device <D0> (<bus id>) -- 4/4 cores free"}`
4. Close the dropdown (highlight, clear, then): `POST /_agent/toggle_dropdown` `{"client_id", "label":"Devices (select one or more)"}` → `{"ok":true,"action":"closed","is_open":false}`

5. Re-set the cores to the model's own value (1 for the primary, 3 for the secondary): `POST /_agent/set_field` `{"client_id", "label":"Cores on Device <D> (<F>/4 free)", "value":"<C>"}` → `{"ok":true,"kind":"input"}`

**Verification**: `GET /_agent/state` — for each model `"Devices (select one or more)"` reads `Device <D> (<bus id>) -- <F>/4 cores free` with `<D>` in the health check's index list, and the cores field reads the model's own value; both models name the same `<D>`.

**Notes**: never leave `Devices` empty — add the new device before removing the old one. Highlight then clear before each call, as everywhere else.

## 9. Generate the pipeline

**9a. Record the baseline** — `GET /_agent/notifications` with `since_id=0`, record the current max `id`.

**9b. Generate it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Generate Pipeline", "text":"Generate pipeline"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Generate Pipeline"}`
→ `{"ok":true,"kind":"button","text":"Generate Pipeline"}`

**Verification**: `GET /_agent/notifications` with `since_id=<baseline>` → `"type":"positive"` `"Generated two-stage cascade pipeline"`; `GET /_agent/graph` → 5 nodes (`input`, `net` with `axnet` `yolox-m-coco-onnx`, `Filter`, `ROI`, `sink`) and 4 edges; the primary `net` node reads `"device":<D>`, `"cores":1`, `"meta_key_override":"det"`; the input node reads `"imdecode_threads":16`.

## 10. Fit view

**10a. Click fit view** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"fit view", "text":"Fit view"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"fit view"}`
→ `{"ok":true,"kind":"button","text":""}`

**Verification**: `GET /_agent/screenshot` — the five nodes `input → net: yolox-m-coco-onnx → Filter → ROI → sink` are in frame.

## 11. Generate, verify and save the YAML

**11a. Generate it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Generate Config YAML", "text":"Generate Config YAML"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Generate Config YAML"}`
→ `{"ok":true,"kind":"button","text":"boltGenerate Config YAML"}`

**11b. Save it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save YAML"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`

**Verification**: after 11a, `GET /_agent/state` → `"dialog_open":true` with buttons `"Cancel"`/`"Save"` and a `"File name"` field (`"cascade-demo"`); parse the YAML (the value of the unlabeled dialog field) and check:
- `nets.net_1.axnet_config` is `net-0;devices:<D>-1` (device `<D>`, 1 core) with `meta_key_override: det`;
- `nets.roi_1_model_a.axnet_config` is `net-0;devices:<D>-3` (the same device `<D>`, 3 cores) with `meta_key_override: pose`;
- the `filter_1` node has `meta_key: det` and `classes: [0]`;
- `roi_1_roi_iter` / `roi_1_roi_collect` use `meta_key: det` and `cls_meta_key: pose`;
- `imdecode_threads: 16`, `imdecode_queue_depth: 32`, `imdecode_queue_timeout_ms: 20000`, and `use_axinference_net_opencl: --disable-opencl`.

After 11b, `GET /_agent/notifications` → `"type":"positive"` `"Wrote <workdir>/client/ui/gui/generated_configs/cascade-demo.yaml"`.

**Notes**: in `axnet_config`, `devices:<D>-<N>` means device `<D>` with `<N>` cores, so the two nets sharing device `<D>` is visible directly from the two strings.

## 12. Compile and launch

**12a. Record the baseline** — `GET /_agent/notifications` with `since_id=0`, record the current max `id`.

**12b. Click Compile and Launch** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Compile and Launch Pipeline", "text":"Compile and launch"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Compile and Launch Pipeline"}`
→ `{"ok":true,"kind":"button","text":"buildCompile and Launch Pipeline"}`
(poll `GET /_agent/notifications` with `since_id=<baseline>` until `"Launched"` appears).

**Verification**: `GET /_agent/notifications` → two `"type":"positive"` entries, in order: `"Compiled 1 pipeline spec(s) and sent to the host server: ..."`, then `"Launched 1 pipeline(s)"`.

## 13. Switch to the Benchmarking tab

`POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Benchmarking", "text":"Benchmarking tab"}`
→ `{"ok":true,"id":"<anno-id>","kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Benchmarking"}`
→ `{"ok":true,"kind":"tab","text":"Benchmarking"}`

**Verification**: `GET /_agent/state` — `"tabs"` shows `Benchmarking` active and `"sources"` reads `{}`.

## 14. Open the drawer and confirm the pipeline

**14a. Open it** — `POST /_agent/hover` `{"client_id", "text":"benchmark settings edge", "action":"enter"}`
→ `{"ok":true,"text":""}`

**14b. Confirm the endpoint and pipeline id** — `GET /_agent/state` — the drawer's `"Inference endpoint(s)"` and `"Pipeline ID(s) for backpressure monitoring"` fields.
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Inference endpoint(s)", "text":"Pipeline successfully initialized"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Pipeline ID(s) for backpressure monitoring", "text":"Pipeline successfully initialized"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/state` — `"drawer"` reads `{"open":true,...}`; `"Inference endpoint(s)"` reads `<host>:<port>` and `"Pipeline ID(s) for backpressure monitoring"` reads the launched pipeline's id (`cascade-demo`); both auto-fill from the pipeline just compiled and launched (§12).

## 15. Configure the live stat-series toggles

1. Per-source latency → off: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Per-source latency", "text":"Per-source latency"}` → `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; only on a mismatch, `POST /_agent/set_field` `{"client_id", "label":"Per-source latency", "value":"false"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
2. CPU utilization → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"CPU utilization", "text":"CPU utilization"}` → `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; only on a mismatch, `POST /_agent/set_field` `{"client_id", "label":"CPU utilization", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
3. Memory utilization → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Memory utilization", "text":"Memory utilization"}` → `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; only on a mismatch, `POST /_agent/set_field` `{"client_id", "label":"Memory utilization", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
4. Aggregate core utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate core utilization %", "text":"Aggregate core utilization %"}` → `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; only on a mismatch, `POST /_agent/set_field` `{"client_id", "label":"Aggregate core utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
5. Aggregate MVM utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate MVM utilization %", "text":"Aggregate MVM utilization %"}` → `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; only on a mismatch, `POST /_agent/set_field` `{"client_id", "label":"Aggregate MVM utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
6. Aggregate DDR utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate DDR utilization %", "text":"Aggregate DDR utilization %"}` → `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; only on a mismatch, `POST /_agent/set_field` `{"client_id", "label":"Aggregate DDR utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
7. Close the drawer: `POST /_agent/hover` `{"client_id", "text":"benchmark settings drawer", "action":"leave"}` → `{"ok":true,"text":"Advanced Settings..."}`

**Verification**: `GET /_agent/state` — `"drawer"` reads `{"open":false,...}`, and the six toggles read `checked:false/true/true/true/true/true` respectively.

**Notes**: the toggles persist across page reloads, so each is usually already correct and only highlighted; `set_field` is called only on a mismatch. The drawer's lower toggles can be reported at the same clipped `rect` — the highlight still resolves.

## 16. Add one image source

**16a. Open the dialog** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add file", "text":"Add file"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Add file"}`
→ `{"ok":true,"kind":"button","text":"add_photo_alternateAdd file"}`

**16b. Select the file** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"File dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"options":[{"text":".. (up)","selected":false},...,{"text":"dancing_frame_t15_480p.jpg","selected":false},...]}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"Select dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"File / folder", "value":"dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"kind":"select","text":"dancing_frame_t15_480p.jpg"}`

**16c. Set the source count** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Count", "text":"Count field"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Count", "value":"1"}`
→ `{"ok":true,"kind":"input"}`

**16d. Set the per-source FPS** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"FPS", "text":"FPS field"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"FPS", "value":"20"}`
→ `{"ok":true,"kind":"input"}`

**16e. Open it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Open", "text":"Open"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Open"}`
→ `{"ok":true,"kind":"button","text":"Open"}`

**Verification**: `GET /_agent/state` — `"sources"` holds one entry with `"status":"live"`, `"has_frame":true`, `"capture_fps"` and `"infer_fps"` near the set FPS, `"det_count"` > 0, `"infer_errors":0` and `"backpressure_active":false`; it appears a few seconds after Open.

## 17. Clear the plot and let the pipeline settle

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"plot refresh", "text":"Clear plot"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"plot refresh"}`
→ `{"ok":true,"kind":"button","text":"refresh"}`
(wait about 30 seconds for the cleared plot to refill before reading it).

**Verification**: `GET /_agent/state` (read it a few times) — the source stays `"live"` with `"infer_fps"` hovering around the set FPS, `"latency_ms"` steady (a few hundred milliseconds or less for one source), `"infer_errors":0`. `GET /_agent/screenshot` with `client_id`, `max_width=1280`, `quality=0.7` — the Aggregate FPS series is flat near the set FPS and the CPU/Memory series are populated, with no error series.

**Notes**: the `(V/L)LM Chat` panel below the plot lists the last launched (V/L)LM server, not this cascade; ignore it here.

## 18. Remove all sources

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete_sweep", "text":"Remove all sources"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"delete_sweep"}`
→ `{"ok":true,"kind":"button","text":"delete_sweep"}`

**Verification**: `GET /_agent/notifications` — `"type":"positive"` `"removed 1 source(s)"`; `GET /_agent/state` — `"sources"` reads `{}`.

## 19. Clean up

**19a. Switch to the Pipeline Editor tab** — `POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Pipeline Editor", "text":"Pipeline Editor tab"}`
→ `{"ok":true,"id":"<anno-id>","kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Pipeline Editor"}`
→ `{"ok":true,"kind":"tab","text":"Pipeline Editor"}`

**19b. Force Stop All** — repeat §2 (button, then its confirm dialog).

**19c. Clear the canvas** — repeat §3 (button, then its "Yes" prompt).

**Verification**: `GET /_agent/notifications` — `"type":"positive"` `"Force-stopped 1 pipeline process(es): <pid>"` (it can take about 20 seconds to appear) then `"No tracked vLLM/LLM servers were running"`; `GET /_agent/graph` → `{"nodes":[],"edges":[]}`.
