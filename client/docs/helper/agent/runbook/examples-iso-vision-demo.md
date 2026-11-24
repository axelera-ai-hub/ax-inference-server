# Examples: ISO Vision Demo

Runbook for the palette's **Examples** group: opening the pre-built
**Isovision Demo** wizard instead of building the pipeline node by node.
Same host and conventions as the other sections.

---

## 1. Confirm the target session

`GET /_agent/sessions`
→ `{"sessions":[{"client_id":"<client_id>","has_socket_connection":true}]}`

**Verification**: response body itself — confirms `<client_id>` is
connected and is the only session.

**Notes**: if a later call returns `{"detail":"no connected client with id
'<client_id>'"}`, the browser page reconnected under a new `client_id`;
repeat this sub-section and redo the interrupted step.

## 2. Force Stop All (button → confirm dialog → confirm)

**2a. Baseline notifications** — `GET /_agent/notifications` with
`since_id=0`, record the current max `id`.

**2b. Highlight the button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"FORCE STOP ALL", "text":"Force stop all button"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**2c. Clear the highlight** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**2d. Click it** — `POST /_agent/click` `{"client_id", "text":"FORCE STOP ALL"}`
→ `{"ok":true,"kind":"button","text":"dangerousForce Stop All"}`
(opens a confirmation dialog with `"Cancel"`/`"Force stop all"` buttons).

**2e. Highlight the dialog's confirm button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force stop all", "text":"Confirm force stop"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**2f. Clear the highlight** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**2g. Click it** — `POST /_agent/click` `{"client_id", "text":"Force stop all"}`
→ `{"ok":true,"kind":"button","text":"Force stop all"}`

**Verification**: `GET /_agent/notifications` with `since_id=<baseline>`
→ two new `"type":"info"` notifications:
`"No axinferencenet_grpc processes were running"`,
`"No tracked vLLM/LLM servers were running"`.

**Notes**: that is the idle-host result. If pipelines are still running
from an earlier launch, the first notification is instead `"type":"positive"`
`"Force-stopped N pipeline process(es): <pid>, ..."` (N = the number of
launched pipelines), followed by the same `"No tracked vLLM/LLM servers
were running"` info notification; it can take several seconds to appear.

## 3. Clear the canvas (button → confirm prompt → Yes)

**3a. Highlight the clear-canvas icon** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete", "text":"Clear canvas button"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**3b. Clear the highlight** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**3c. Click it** — `POST /_agent/click` `{"client_id", "text":"delete"}`
→ `{"ok":true,"kind":"button","text":"delete"}`
(opens a "Clear canvas?" confirm prompt with `"No"`/`"Yes"` buttons).

**3d. Highlight "Yes"** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Yes", "text":"Confirm clear canvas"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`

**3e. Clear the highlight** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**3f. Click it** — `POST /_agent/click` `{"client_id", "text":"Yes"}`
→ `{"ok":true,"kind":"button","text":"Yes"}`

**Verification**: `GET /_agent/graph` → `{"nodes":[],"edges":[]}`.

**Notes**: the confirm prompt is a custom overlay, so
`/_agent/state`'s `"dialog_open"` stays `false` while it shows.

## 4. Open the Isovision Demo wizard

**4a. Highlight the "Examples" group** — `POST /_agent/highlight` `{"client_id", "kind":"text", "target":"Examples", "text":"Open Examples group"}`
→ `{"ok":true,"id":"<anno-id>","kind":"text","rect":{...}}`

**4b. Clear the highlight** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**4c. Click it** — `POST /_agent/click` `{"client_id", "text":"Examples"}`
→ `{"ok":true,"kind":"tree-node","text":"play_arrowExamples"}`

**4d. Highlight the "Isovision Demo" leaf** — `POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Isovision Demo", "text":"Click Isovision Demo"}`
→ `{"ok":true,"id":"<anno-id>","kind":"palette","rect":{...}}`

**4e. Clear the highlight** — `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**4f. Click it** — `POST /_agent/click` `{"client_id", "text":"Isovision Demo"}`
→ `{"ok":true,"kind":"tree-node","text":"scienceIsovision Demo"}`

**Verification**: `GET /_agent/state` → `"dialog_open":true`; the dialog's
buttons are `"Run Health Check"`, `"Cancel"`, `"Generate Pipelines"`, with
fields `"Model (.axnet, from host server)"` (`"yolox-m-coco-onnx"`),
`"imdecode_threads override (blank = auto, 4x pinned cores)"`,
`"imdecode_queue_depth"`, `"imdecode_queue_timeout_ms"` and a
`"Use prebuilt models (axdownloadmodel catalog instead of buil..."`
toggle. `GET /_agent/graph` stays `{"nodes":[],"edges":[]}`.

**Notes**:
- **4f**: clicking the leaf opens the wizard directly; `add_node` with
  `"Isovision Demo"` returns `{"ok":false,"error":"unknown_label",...}`
  since it only knows the single-node labels.

## 5. Select the detection model

**5a. Open the dropdown** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model (.axnet, from host server)", "text":"Model dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Model (.axnet, from host server)"}`
→ `{"ok":true,"options":[{"text":"retinaface-mobilenet0.25-widerface-onnx","selected":false},...,{"text":"yolox-m-coco-onnx","selected":true}]}`

**5b. Pick "yolox-m-coco-onnx"** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model (.axnet, from host server)", "text":"Select yolox-m-coco-onnx"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Model (.axnet, from host server)", "value":"yolox-m-coco-onnx"}`
→ `{"ok":true,"kind":"select","text":"yolox-m-coco-onnx"}`

**Verification**: `POST /_agent/read_dropdown_options` → `{"ok":false,"error":"not_open"}` (the dropdown closed itself); `GET /_agent/state` shows the field's `"value":"yolox-m-coco-onnx"`.

**Notes**: `yolox-m-coco-onnx` is already selected when the wizard opens; `set_field` still selects it explicitly and closes the dropdown, so no separate close call is needed.

## 6. Run the device health check

**6a. Baseline notifications** — `GET /_agent/notifications` with `since_id=0`, record the current max `id`.

**6b. Run it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Run Health Check", "text":"Run health check"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Run Health Check"}`
→ `{"ok":true,"kind":"button","text":"Run Health Check"}`
(poll `GET /_agent/state` until the dialog's buttons include `"Throughput Test"`, about a minute).

**Verification**: `GET /_agent/screenshot` with `client_id`, `max_width=1280`, `quality=0.6` — the dialog reads `<H> / <T> device(s) healthy (indices: <comma-separated healthy device indices>)`, where `<H>` is the number of healthy devices out of `<T>` on the host; `<H>` must be at least 1 for the remaining steps to apply. `GET /_agent/notifications` with `since_id=<baseline>` returns no new entries.

**Notes**: the result is shown only in the dialog, not as a notification, and `GET /_agent/get_text` returns `"ambiguous"` for `"healthy"`, so read it from the screenshot. The `Throughput Test`, `Seconds`, `Devices per pipeline`, `Pin CPU/NUMA` and cores-per-instance controls only appear after a successful check.

## 7. Run the throughput test (performance gate)

**7a. Set the duration to 5 seconds** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Seconds", "text":"Throughput test duration"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Seconds", "value":"5"}`
→ `{"ok":true,"kind":"input"}`

**7b. Run it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Throughput Test", "text":"Run throughput test"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Throughput Test"}`
→ `{"ok":true,"kind":"button","text":"Throughput Test"}`

**Verification**: `GET /_agent/state` shows `"Seconds"` = `"5"`; after about 15 seconds `GET /_agent/screenshot` reads `Aggregate: <X> FPS across <H>/<H> device(s)`, covering every healthy device from the health check. Record `<X>`: it is the performance gate the Benchmarking tab must reach.

## 8. Configure the pipeline settings

**8a. Keep "Devices per pipeline" at 1** — `GET /_agent/state` shows `"Devices per pipeline"` = `"1"`; no call needed.

**8b. Enable Pin CPU/NUMA** — `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Pin CPU/NUMA (taskset + numactl)", "text":"Enable CPU/NUMA pinning"}`
→ `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Pin CPU/NUMA (taskset + numactl)", "value":"true"}`
→ `{"ok":true,"kind":"toggle","changed":true}`

**8c. Keep cores per instance at the default** — `GET /_agent/state` shows `"4 core(s) per instance"`; no call needed.

**8d. Set imdecode_threads to 16** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"imdecode_threads override (blank = auto, 4x pinned cores)", "text":"imdecode threads"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"imdecode_threads override (blank = auto, 4x pinned cores)", "value":"16"}`
→ `{"ok":true,"kind":"input"}`

**Verification**: `GET /_agent/state` — the dialog's toggle `"Pin CPU/NUMA (taskset + numactl)"` is `true` and the field `"imdecode_threads override (blank = auto, 4x pinned cores)"` is `"16"`.

## 9. Generate the pipelines

**9a. Click Generate Pipelines** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Generate Pipelines", "text":"Generate pipelines"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Generate Pipelines"}`
→ `{"ok":true,"kind":"button","text":"Generate Pipelines"}`

**Verification**: `GET /_agent/notifications` with `since_id=<baseline>` → `"type":"positive"` `"Generated <H> isovision pipeline(s), 1 device(s) each"` (one pipeline per healthy device at 1 device per pipeline); `GET /_agent/state` → `"dialog_open":false`; `GET /_agent/graph` shows `3 × <H>` nodes (Input, model, Sink per pipeline) and `2 × <H>` edges.

## 10. Fit view

**10a. Click fit view** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"fit view", "text":"Fit view"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"fit view"}`
→ `{"ok":true,"kind":"button","text":""}`

**Verification**: `GET /_agent/screenshot` — all `<H>` pipelines are in frame.

## 11. Generate and save the YAML

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

**Verification**: after 11a, `GET /_agent/state` → `"dialog_open":true` with buttons `"Cancel"`/`"Save"` and a `"File name"` field (`"iso-detect_plus<H-1>"`); its YAML parses to `nets` with `<H>` entries, `pipelines` with `<H>` entries, `imdecode_threads: 16`, `taskset_cpus` set on each, and `use_axinference_net_opencl: --disable-opencl`. After 11b, `GET /_agent/notifications` → `"type":"positive"` `"Wrote <workdir>/client/ui/gui/generated_configs/<file name>.yaml"`.

**Notes**: the YAML is the value of the unlabeled dialog field in `/_agent/state`'s `"fields"`; parse it to count entries.

## 12. Compile and launch

**12a. Record the baseline** — `GET /_agent/notifications` with `since_id=0`, record the current max `id`.

**12b. Click Compile and Launch** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Compile and Launch Pipeline", "text":"Compile and launch"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Compile and Launch Pipeline"}`
→ `{"ok":true,"kind":"button","text":"buildCompile and Launch Pipeline"}`
(poll `GET /_agent/notifications` with `since_id=<baseline>` until `"Launched"` appears).

**Verification**: `GET /_agent/notifications` → two `"type":"positive"` entries, in order: `"Compiled <H> pipeline spec(s) and sent to the host server: ..."`, then `"Launched <H> pipeline(s)"`.

## 13. Switch to the Benchmarking tab and confirm the pipelines

`POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Benchmarking", "text":"Benchmarking tab"}`
→ `{"ok":true,"id":"<anno-id>","kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Benchmarking"}`
→ `{"ok":true,"kind":"tab","text":"Benchmarking"}`
`POST /_agent/hover` `{"client_id", "text":"benchmark settings edge", "action":"enter"}`
→ `{"ok":true,"text":""}`
`GET /_agent/state` — the drawer's `"Inference endpoint(s)"` and `"Pipeline ID(s) for backpressure monitoring"` fields.
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Inference endpoint(s)", "text":"Pipeline successfully initialized"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Pipeline ID(s) for backpressure monitoring", "text":"Pipeline successfully initialized"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/hover` `{"client_id", "text":"benchmark settings drawer", "action":"leave"}`
→ `{"ok":true,"text":"Advanced Settings..."}`

**Verification**: `GET /_agent/state` — `"tabs"` shows `Benchmarking` active; both drawer fields list one entry per launched pipeline (`<H>` entries each, one port and one pipeline id per pipeline); `"drawer"` reads `{"open":false,...}`; `"sources"` reads `{}`.

**Notes**: set the drawer's stat toggles (Per-source latency off; CPU, Memory, Aggregate core, Aggregate MVM and Aggregate DDR utilization on) exactly as in "Benchmarking Vision Pipelines" §4 ([benchmarking-vision.md](benchmarking-vision.md)); they persist across page reloads, so each one is usually already correct and `set_field` is only called for a mismatch.

## 14. Add sources within the performance gate

Pick `<S>` and `<F>` so that `<S> × <F>` is at or just below the recorded gate `<X>` (§7) — each image source supports up to 500 FPS.

**14a. Open the dialog** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add file", "text":"Add file"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Add file"}`
→ `{"ok":true,"kind":"button","text":"add_photo_alternateAdd file"}`

**14b. Select the file** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"File / folder dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"options":[...,{"text":"dancing_frame_t15_480p.jpg","selected":false},...]}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"Select dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"File / folder", "value":"dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"kind":"select","text":"dancing_frame_t15_480p.jpg"}`

**14c. Set the source count** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Count", "text":"Count field"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Count", "value":"<S>"}`
→ `{"ok":true,"kind":"input"}`

**14d. Set the per-source FPS** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"FPS", "text":"FPS field"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"FPS", "value":"<F>"}`
→ `{"ok":true,"kind":"input"}`

**14e. Open it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Open", "text":"Open"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Open"}`
→ `{"ok":true,"kind":"button","text":"Open"}`

**Verification**: `GET /_agent/state` — `"sources"` holds `<S>` entries, each `"status":"live"`, `"has_frame":true`, with `"det_count"` > 0; summed `"infer_fps"` is close to `<S> × <F>` and each `"latency_ms"` is in the tens of milliseconds.

## 15. Read the within-gate result

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"plot refresh", "text":"Clear plot"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"plot refresh"}`
→ `{"ok":true,"kind":"button","text":"refresh"}`
(wait about a minute for the cleared plot to refill before reading it.)

**Verification**: `GET /_agent/screenshot` with `client_id`, `max_width=1280`, `quality=0.7` — the Aggregate FPS series is flat near `<S> × <F>` (at or below `<X>`) with no error series; `GET /_agent/state` — every source still `"live"`.

## 16. Remove all sources

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete_sweep", "text":"Remove all sources"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"delete_sweep"}`
→ `{"ok":true,"kind":"button","text":"delete_sweep"}`

**Verification**: `GET /_agent/notifications` — `"type":"positive"` `"removed <S> source(s)"`; `GET /_agent/state` — `"sources"` reads `{}`.

## 17. Add sources beyond the performance gate (overload run)

Pick `<S2>` and `<F>` so that `<S2> × <F>` exceeds `<X>` by roughly 10–15%.

**17a. Open the dialog** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add file", "text":"Add file"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Add file"}`
→ `{"ok":true,"kind":"button","text":"add_photo_alternateAdd file"}`

**17b. Select the file** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"File / folder dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"options":[...,{"text":"dancing_frame_t15_480p.jpg","selected":false},...]}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"Select dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"File / folder", "value":"dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"kind":"select","text":"dancing_frame_t15_480p.jpg"}`

**17c. Set the source count** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Count", "text":"Count field"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Count", "value":"<S2>"}`
→ `{"ok":true,"kind":"input"}`

**17d. Set the per-source FPS** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"FPS", "text":"FPS field"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"FPS", "value":"<F>"}`
→ `{"ok":true,"kind":"input"}`

**17e. Open it** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Open", "text":"Open"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Open"}`
→ `{"ok":true,"kind":"button","text":"Open"}`

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"plot refresh", "text":"Clear plot"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"plot refresh"}`
→ `{"ok":true,"kind":"button","text":"refresh"}`
(wait about a minute for the cleared plot to refill before reading it.)

**Verification**: `GET /_agent/state` — `"sources"` holds `<S2>` entries, all still `"status":"live"` with `"det_count"` > 0; compared with the within-gate run, summed `"infer_fps"` is the same or higher, summed `"capture_fps"` is below `<S2> × <F>`, and every `"latency_ms"` is orders of magnitude larger (seconds instead of tens of milliseconds). `GET /_agent/screenshot` — the Aggregate FPS series is flat, and `GET /_agent/notifications` shows no new error entries.

**Notes**: overload shows up as latency growth and sources being held back below their target FPS, not as dropped sources or errors, so read `"latency_ms"` and `"capture_fps"` rather than only the aggregate. The aggregate can land above `<X>`, since the throughput test is a short sample. Under heavy host load the browser page can reconnect with a new `client_id`; repeat §1, then continue from the interrupted step.

## 18. Tune the layout and measure the aggregate FPS

**18a. Check the host CPU layout** — `lscpu -e=CPU,CORE,MAXMHZ`
`uptime`

**18b. Find the per-device ceiling** — run a one-device layout, then repeat §14 with `Count` = `1` and `FPS` = `<F_probe>`:
`POST /_agent/set_field` `{"client_id", "label":"Count", "value":"1"}`
→ `{"ok":true,"kind":"input"}`
`POST /_agent/set_field` `{"client_id", "label":"FPS", "value":"<F_probe>"}`
→ `{"ok":true,"kind":"input"}`
`GET /_agent/state` with `client_id` (read about 50 s after `Open`, then repeat)
→ `{"sources":{"src-<N>":{"status":"live","has_frame":true,"det_count":<D>,"infer_fps":<R>,"capture_fps":<R>,"latency_ms":<L>,...}},...}`

**18c. Offer `<D>` × `<C>`** — repeat §14 on the `<D>`-device layout with `Count` = `<D>` and `FPS` = `<C>`:
`POST /_agent/set_field` `{"client_id", "label":"Count", "value":"<D>"}`
→ `{"ok":true,"kind":"input"}`
`POST /_agent/set_field` `{"client_id", "label":"FPS", "value":"<C>"}`
→ `{"ok":true,"kind":"input"}`

**18d. Read the aggregate** — `GET /_agent/state` with `client_id`, about 12 times, 5–10 s apart, starting about 50 s after `Open`
→ `{"sources":{"src-<N>":{"infer_fps":<R>,"latency_ms":<L>,...},...},...}`

**Verification**: `GET /_agent/state` — `"sources"` holds `<D>` entries, all `"status":"live"`; the aggregate is the sum of `"infer_fps"` over all sources in each read, and the run's result is the mean, minimum and maximum of those sums against the offered load `<D> × <C>` (at or below the gate `<X>`). A healthy read has every `"latency_ms"` in the tens of milliseconds; the one-device probe in 18b flattens at `<C>` while `"latency_ms"` grows to seconds.

**Notes**:

- **Scope**: use this when the wizard's layout does not reach the throughput the devices can deliver. `<D>` is the number of devices in the layout, `<C>` the per-device ceiling found in 18b, and `<F_probe>` a per-source FPS well above the expected ceiling.
- **18a**: on a CPU with fast and slow cores (`MAXMHZ` differs between CPU groups, for example the first logical CPUs at a higher clock), pinned CPUs on the slow cores run decode and pre/post-processing slower. Pin pipelines to the fast cores while they fit; once the pipelines need more CPUs than the fast cores hold, spreading over the slow cores as well beats sharing the fast ones. Pipelines that each get too few CPUs queue even with free cores elsewhere. A load average well above the CPU count means the layout is CPU-bound.
- **18b**: no special endpoint measures the ceiling. Offer one source more than the device can take; `"infer_fps"` stops rising at the ceiling `<C>` and `"latency_ms"` climbs, which marks saturation.
- **18c**: set the offered load to `<D> × <C>` and keep `Count × FPS` at or below `<X>`. Remove every source (§16) before changing the layout, and add new ones after the new pipelines are up.
- **18d**: the first reads after `Open` show high latency while queues fill; wait about 50 s before reading. A single read is noisy (the sum can move by 10% between reads), so judge a layout on the mean of the reads, not on one value. Roughly 95% of the offered load with latency mostly in the tens of milliseconds is a good result. A sum near the offered load with latency in seconds means the layout is saturated, not healthy; spikes of hundreds of milliseconds mean it is at its limit.
- **18d**: scale in steps (1, 2, 3, ... `<D>` devices). The aggregate should grow roughly linearly; when it stops growing or latency jumps, the host is out of CPU for that many devices, and adding more devices does not help.
- **Changing the layout by hand**: for a layout the wizard cannot express (different `taskset_cpus`, `imdecode_threads`, devices per pipeline, or OpenCL), remove all sources (§16), follow [yaml-save-modify-load.md](yaml-save-modify-load.md) from §2 to §8, and return to 18c with the new layout.
- **Decode threads**: more decode threads (`imdecode_threads`) help only while decode is the bottleneck; change one setting at a time and compare means.

## 19. Clean up

**19a. Remove all sources** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete_sweep", "text":"Remove all sources"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"delete_sweep"}`
→ `{"ok":true,"kind":"button","text":"delete_sweep"}`

**19b. Switch to the Pipeline Editor tab** — `POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Pipeline Editor", "text":"Pipeline Editor tab"}`
→ `{"ok":true,"id":"<anno-id>","kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Pipeline Editor"}`
→ `{"ok":true,"kind":"tab","text":"Pipeline Editor"}`

**19c. Force Stop All** — repeat §2 (button, then its confirm dialog).

**19d. Clear the canvas** — repeat §3 (button, then its "Yes" prompt).

**Verification**: `GET /_agent/notifications` — `"removed <S2> source(s)"`, then `"Force-stopped <H> pipeline process(es): <pid>, ..."` and `"No tracked vLLM/LLM servers were running"`; `GET /_agent/graph` → `{"nodes":[],"edges":[]}`.
