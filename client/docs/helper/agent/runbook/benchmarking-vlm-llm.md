# Benchmarking VLMs and LLMs

A separate workflow from the [VLM Demo](vlm-demo.md): benchmarking a `(V/L)LM`
node that is already compiled and launched (e.g. by completing the VLM
Demo's steps 1-11 first). Runbook documenting the exact GUI
`/_agent/*` FastAPI calls used to drive the Benchmarking tab's `(V/L)LM
Chat` panel.

## 1. Switch to the Benchmarking tab

`POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Benchmarking", "text":"Benchmarking tab"}`
→ `{"ok":true,"kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Benchmarking"}`
→ `{"ok":true,"kind":"tab","text":"Benchmarking"}`

**Verification**: `GET /_agent/state` — `"tabs"` reads
`[{"text":"Pipeline Editor","active":false},{"text":"Benchmarking","active":true}]`.

## 2. Open the "Advanced Settings" right drawer

`POST /_agent/hover` `{"client_id", "text":"benchmark settings edge", "action":"enter"}`
→ `{"ok":true,"text":""}`

**Verification**: `GET /_agent/state` — `"drawer"` reads
`{"open":true,"rect":{...}}`.

**Notes**: same edge-hover/no-clickable-control behavior as the
[Benchmarking Vision Pipelines](benchmarking-vision.md) workflow's equivalent step — see that
section's Notes for the mouseenter/mouseleave mechanics.

## 3. Configure the live stat-series toggles

1. Per-source latency → off: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Per-source latency", "text":"Per-source latency"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `true`, `POST /_agent/set_field` `{"client_id", "label":"Per-source latency", "value":"false"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
2. CPU utilization → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"CPU utilization", "text":"CPU utilization"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"CPU utilization", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
3. Memory utilization → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Memory utilization", "text":"Memory utilization"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Memory utilization", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
4. Aggregate core utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate core utilization %", "text":"Aggregate core utilization %"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Aggregate core utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
5. Aggregate MVM utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate MVM utilization %", "text":"Aggregate MVM utilization %"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Aggregate MVM utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
6. Aggregate DDR utilization % → on: `POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"Aggregate DDR utilization %", "text":"Aggregate DDR utilization %"}` → `{"ok":true,"kind":"toggle","rect":{...}}`; `GET /_agent/state` — the toggle's `"checked"`; if `false`, `POST /_agent/set_field` `{"client_id", "label":"Aggregate DDR utilization %", "value":"true"}` → `{"ok":true,"kind":"toggle","changed":true}`; `POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`.
7. Close the drawer: `POST /_agent/hover` `{"client_id", "text":"benchmark settings drawer", "action":"leave"}` → `{"ok":true,"text":"Advanced Settings..."}`

**Verification**: `GET /_agent/state` — `"drawer"` reads `{"open":false,...}`,
and the six toggles read `checked:false/true/true/true/true/true`
respectively, matching their targets.

**Notes**: unlike Vision Pipeline benchmarking, this drawer has no
pipeline to confirm initialized here — its `"Inference endpoint(s)"` /
`"Pipeline ID(s) for backpressure monitoring"` fields describe whichever
Vision pipeline was last launched, not the `(V/L)LM` node, so this
workflow has no equivalent to that confirmation step; the chat panel's
own server field (step 4) is the real confirmation that the `(V/L)LM`
node is initialized. Each toggle only calls `set_field` when its current
`checked` value doesn't already match its target — left alone otherwise.

## 4. Verify the VLM endpoint in the chat panel

`GET /_agent/state` — the `"(V/L)LM server"` field's `"value"`.
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"(V/L)LM server", "text":"VLM server dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: the field's `"value"` reads `"<(V/L)LM node_id> (<N>
instance(s), port(s) <port>)"` (e.g. `"model-vllm-vlm-10 (1 instance,
port(s) 8001)"`) — confirms the node launched by the VLM Demo's Compile
and Launch Pipeline step is live and visible here.

**Notes**: when only one `(V/L)LM` server is running, this field already
holds that value by default and `/_agent/toggle_dropdown` on it does not
reliably open a visible popup (repeated calls return
`{"ok":true,"action":"opened","is_open":false}`) — reading the field's
`"value"` directly, as above, is the authoritative check, not
`read_dropdown_options`.

## 5. Send a text-only prompt

**5a. Type the message** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Message", "text":"Message input"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Message", "value":"Tell us a joke."}`
→ `{"ok":true,"kind":"input"}`

**5b. Send it** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"send", "text":"Send"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"send"}`
→ `{"ok":true,"kind":"button","text":"sendSend"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: `GET /_agent/get_text` with `contains=<a substring
unique to the reply>` → `{"ok":true,"text":"[<(V/L)LM node_id> · TTFT
<N>s · <N> tok/s]  <reply text>"}` (e.g. `{"ok":true,"text":"[model-vllm-
vlm-10 · TTFT 0.62s · 43.9 tok/s]  What's the best way to tell a joke?
..."}`). Optionally, for extra assurance, `POST /_agent/screenshot`
`{"client_id"}` → `{"ok":true,"image_base64":"..."}` and inspect the
decoded image to visually confirm the same reply/metrics bubble.

**Notes**: `contains` must be specific enough to match only this one
message — a bare metrics label like `"TTFT"` matches every message
bubble plus the running-average caption at once and returns
`{"ok":false,"error":"ambiguous","matched_count":3}`; a phrase from the
reply's own text is unambiguous. The running average across all calls
made so far is also readable this way: `GET /_agent/get_text` with
`contains="avg (last"` → `{"ok":true,"text":"avg (last 1): TTFT 0.62s ·
43.9 tok/s"}`. `/_agent/get_text` is the cheaper, direct, authoritative
path for both the reply text and its TTFT/tokens-per-second — a
screenshot is a slower, visual cross-check layered on top for extra
certainty, not a replacement.

## 6. Send a prompt with attached images

**6a. Attach the first image** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add image(s)", "text":"Add image(s)"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Add image(s)"}`
→ `{"ok":true,"kind":"button","text":"add_photo_alternateAdd image(s)"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
(opens an "Add image" dialog with a "File / folder" dropdown and
"Cancel"/"Add" buttons.)
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"File / folder dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"options":[...,{"text":"dancing_frame_t15_480p.jpg","selected":false},{"text":"dancing_frame_t5_480p.jpg","selected":false},...]}`
`POST /_agent/set_field` `{"client_id", "label":"File / folder", "value":"dancing_frame_t15_480p.jpg"}`
→ `{"ok":true,"kind":"select","text":"dancing_frame_t15_480p.jpg"}`
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add", "text":"Add image"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Add"}`
→ `{"ok":true,"kind":"button","text":"Add"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**6b. Attach the second image** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add image(s)", "text":"Add image(s)"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Add image(s)"}`
→ `{"ok":true,"kind":"button","text":"add_photo_alternateAdd image(s)"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"File / folder dropdown"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/set_field` `{"client_id", "label":"File / folder", "value":"dancing_frame_t5_480p.jpg"}`
→ `{"ok":true,"kind":"select","text":"dancing_frame_t5_480p.jpg"}`
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add", "text":"Add image"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"Add"}`
→ `{"ok":true,"kind":"button","text":"Add"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**6c. Type the message** —
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Message", "text":"Message input"}`
→ `{"ok":true,"kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Message", "value":"Describe the activity in these images."}`
→ `{"ok":true,"kind":"input"}`

**6d. Send it** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"send", "text":"Send"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/click` `{"client_id", "text":"send"}`
→ `{"ok":true,"kind":"button","text":"sendSend"}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`

**Verification**: image count readout reads `"2/8 images attached, 6
more allowed"` after 6b; `GET /_agent/get_text` with `contains=<a
substring unique to the reply>` → `{"ok":true,"text":"[<(V/L)LM node_id>
· TTFT <N>s · <N> tok/s]  <reply text>"}` describing the attached
images' actual content (e.g. `{"ok":true,"text":"[model-vllm-vlm-10 ·
TTFT 2.57s · 45.1 tok/s]  The image depicts a group of people dancing in
a dance studio. ..."}`), confirming the model actually received and
processed both images. Optionally, for extra assurance, `POST
/_agent/screenshot` `{"client_id"}` → `{"ok":true,"image_base64":"..."}`
and inspect the decoded image to visually confirm the same reply/metrics
bubble and the two attached image thumbnails.

**Notes**: the "File / folder" dropdown's option text comes from the
host's media directory listing, same mechanism as the Benchmarking
Vision Pipelines "Add a file source" step — use the exact listed
filename, not a spoken/transcribed approximation of it. Each "Add
image(s)" dialog attaches one file per pass and closes itself once
"Add" is clicked — repeat the whole dialog round-trip once per image
rather than multi-selecting in a single pass.

## 7. Clear the chat interface

`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Clear", "text":"Clear chat"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Clear"}`
→ `{"ok":true,"kind":"button","text":"Clear"}`

**Verification**: `GET /_agent/state` — the `"Message"` field's
`"value"` reads `""`. `GET /_agent/get_text` with
`contains="images attached"` → `{"ok":true,"text":"0/8 images attached
(8 more allowed)"}`.

## 8. Switch to the Pipeline Editor tab

`POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Pipeline Editor", "text":"Pipeline Editor tab"}`
→ `{"ok":true,"kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Pipeline Editor"}`
→ `{"ok":true,"kind":"tab","text":"Pipeline Editor"}`

**Verification**: `GET /_agent/state` — `"tabs"` reads
`[{"text":"Pipeline Editor","active":true},{"text":"Benchmarking","active":false}]`.

## 9. Force Stop All and clear the canvas

**9a. Force Stop All (button → confirm dialog → confirm)** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force Stop All", "text":"Force Stop All"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Force Stop All"}`
→ `{"ok":true,"kind":"button","text":"dangerousForce Stop All"}`
(opens a confirmation dialog with `"Cancel"`/`"Force stop all"` buttons.)
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Force stop all", "text":"Confirm Force Stop All"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Force stop all"}`
→ `{"ok":true,"kind":"button","text":"Force stop all"}`

**9b. Clear the canvas (button → confirm prompt → Yes)** —
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"delete", "text":"Clear canvas button"}`
(icon ligature name `"delete"`)
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"delete"}`
→ `{"ok":true,"kind":"button","text":"delete"}`
(opens a "Clear canvas?" confirm prompt with `"No"`/`"Yes"` buttons.)
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Yes", "text":"Confirm clear canvas"}`
→ `{"ok":true,"kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Yes"}`
→ `{"ok":true,"kind":"button","text":"Yes"}`

**Verification**: `GET /_agent/notifications` — two new entries:
`"type":"info"` `"No axinferencenet_grpc processes were running"`, then
`"type":"positive"` `"Stopped 1 vLLM/LLM server(s): <(V/L)LM node_id>"`.
A follow-up `GET /_agent/graph` → `{"nodes":[],"edges":[]}`.

**Notes**: same two custom confirmation overlays as the Benchmarking
Vision Pipelines workflow's equivalent closing steps — neither sets
`/_agent/state`'s `"dialog_open"` to `true`; read `/_agent/state`'s
`"buttons"` list for their `"Cancel"`/`"Force stop all"` or
`"No"`/`"Yes"` entries instead if confirmation one is open is needed
before clicking.
