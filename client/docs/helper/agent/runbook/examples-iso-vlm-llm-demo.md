# Examples: Iso-VLM/LLM-Demo

Runbook for the palette's **Examples** group: opening the **Iso-VLM/LLM-Demo**
wizard, which deploys N independent (V/L)LM pipelines at once (each an
Input → (V/L)LM → Sink chain with its own model, device, settings and port),
launching them, and benchmarking them from the Benchmarking tab's (V/L)LM
Chat panel by looping a shared **prompt library** against each server in
turn. No individual chat messages are sent; the prompt library is the only
load. Same host and conventions as the other topics.

Placeholders: `<N>` = number of pipelines, `<i>` = pipeline index (1..`<N>`),
`<M>` = the small VLM model option, `<D_i>` = the device chosen for pipeline
`<i>`, `<P>` = base port, `<S_i>` = server `vllm-<i>` (port `<P>`+`<i>`−1),
`<T1>`/`<T2>` = the two prompt titles.

## 1. Confirm the target session

`GET /_agent/sessions`
→ `{"sessions":[{"client_id":"<client_id>","has_socket_connection":true}]}`

**Verification**: response body itself — confirms `<client_id>` is connected and is the only live session.

**Notes**: if a later call returns `{"detail":"no connected client with id '<client_id>'"}`, the browser page reconnected under a new `client_id` (for example after a GUI restart); reload the page, repeat this sub-section and redo the interrupted step.

## 2. Force Stop All (button → confirm dialog → confirm)

**2a. Baseline notifications** — `GET /_agent/notifications`, record the current max `id`.

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

**Verification**: `GET /_agent/notifications` with `since_id=<baseline>` → `"No axinferencenet_grpc processes were running"` and, if servers were running, `"Stopped <K> vLLM/LLM server(s): vllm-1, ..."`.

**Notes**: with a running Vision pipeline the first notification is instead `"Force-stopped N pipeline process(es): <pid>, ..."` and can take several seconds.

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

**Notes**: the click alone only opens the prompt; the canvas is cleared only after **3b**. The prompt is a custom overlay, so `/_agent/state`'s `"dialog_open"` stays `false` while it shows.

## 4. Open the Iso-VLM/LLM-Demo wizard

**4a. Expand the "Examples" group** — `POST /_agent/highlight` `{"client_id", "kind":"text", "target":"Examples", "text":"Open Examples group"}`
→ `{"ok":true,"id":"<anno-id>","kind":"text","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Examples"}`
→ `{"ok":true,"kind":"tree-node","text":"play_arrowExamples"}`

**4b. Open the wizard** — `POST /_agent/highlight` `{"client_id", "kind":"palette", "target":"Iso-VLM/LLM-Demo", "text":"Click Iso-VLM/LLM-Demo"}`
→ `{"ok":true,"id":"<anno-id>","kind":"palette","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Iso-VLM/LLM-Demo"}`
→ `{"ok":true,"kind":"tree-node","text":"scienceIso-VLM/LLM-Demo"}`

**Verification**: `GET /_agent/state` → `"dialog_open":true`; the dialog's field is `"How many parallel pipelines do you want to deploy?"` (default `1`) and its buttons are `"Re-check device health"`, `"Cancel"`, `"Next"`. `GET /_agent/graph` stays `{"nodes":[],"edges":[]}`.

**Notes**: a second click on `Examples` collapses the group again; if `Iso-VLM/LLM-Demo` returns `not_found`, click `Examples` once more.

## 5. Set the pipeline count and check device health

**5a. Set the count** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"How many parallel pipelines do you want to deploy?", "text":"Pipelines = <N>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"How many parallel pipelines do you want to deploy?", "value":"<N>"}`
→ `{"ok":true,"kind":"input"}`

**5b. Run the device health check** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Re-check device health", "text":"Re-check device health"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Re-check device health"}`
→ `{"ok":true,"kind":"button","text":"refreshRe-check device health"}`

**5c. Wait for the result** — poll `GET /_agent/get_text` with `contains="healthy"` until it returns `{"ok":true,"text":"<H>/<T> device(s) healthy (indices: <list>)"}`.

**Verification**: the dialog text reads `<H>/<T> device(s) healthy (indices: <list>)`; also `GET /_agent/notifications` → `"Unhealthy device(s): <device>, ..."` (negative) when any device failed, or `"All selected devices passed the health check"`. Screenshot (`max_width=1280`, `quality=0.5`) to confirm.

**Notes**:
- Run this **before** assigning models and devices: **Next** is blocked with the warning `"Run the device health check first"` until it has run once.
- The button is `disabled: true` while the check runs; the first run can take tens of seconds to minutes. `get_text` is ambiguous while the previous result text is also on screen — match the phrase `healthy`, not `device(s)` (the parentheses break the query string).
- Pick `<D_i>` from the healthy `<list>`, one distinct device per pipeline, in ascending order.

## 6. Configure pipeline `<i>` of `<N>`

Repeat **6a–6e** for `<i>` = 1 .. `<N>`, using the next healthy device `<D_i>` each time.

**6a. Advance** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Next", "text":"Next"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Next"}`
→ `{"ok":true,"kind":"button","text":"Next"}`
(shows `"Pipeline <i> of <N>"` with fields `Model`, `Device`, `temperature`, `Image resize width (px)`, `Image resize height (px)` and the `enable_thinking` / `Is VLM (image input)` switches).

**6b. Model** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model", "text":"Model dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Model"}`
→ `{"ok":true,"action":"opened|closed","is_open":true|false}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Model"}`
→ `{"ok":true,"options":[{"text":"<M>","selected":true}]}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model", "text":"Select <M>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Model", "value":"<M>"}`
→ `{"ok":true,"kind":"select","text":"<M>"}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Model", "text":"Close Model dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Model"}`
→ `{"ok":true,"action":"opened|closed","is_open":true|false}`

**6c. Device** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Device", "text":"Device dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"Device"}`
→ `{"ok":true,"action":"opened|closed","is_open":true|false}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Device"}`
→ `{"ok":true,"options":[{"text":"metis-<bus> (device <n>)  ⚠ FAILED HEALTH CHECK","selected":false},{"text":"metis-<bus> (device <n>)","selected":false},...]}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Device", "text":"Select <D_i>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Device", "value":"metis-<bus> (device <D_i>)"}`
→ `{"ok":true,"kind":"select","text":"metis-<bus> (device <D_i>)"}`

**6d. Switches** — for each label in `enable_thinking`, `Is VLM (image input)`:
`POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"<label>", "text":"<label> on"}`
→ `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"<label>", "value":"true"}`
→ `{"ok":true,"kind":"toggle","changed":true}`

**6e. Numeric fields** — for each (`temperature`,`0.0`), (`Image resize width (px)`,`256`), (`Image resize height (px)`,`256`):
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"<label>", "text":"<label> = <value>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"<label>", "value":"<value>"}`
→ `{"ok":true,"kind":"input"}`

**Verification**: `GET /_agent/state` → `Model`=`<M>`, `Device`=`metis-<bus> (device <D_i>)`, `temperature`=`0.0`, width/height=`256`; screenshot shows both switches on.

**Notes**:
- `Device` lists every device; failed ones carry the suffix `⚠ FAILED HEALTH CHECK` — never select one (the wizard warns, without blocking, if one is chosen). Each pipeline defaults to the first healthy device, so set `<D_i>` explicitly for `<i>` > 1.
- `Image resize width/height (px)` hold the default `512` until set; they apply only with `Is VLM (image input)` on.
- `set_field` on a select auto-closes it; the extra `toggle_dropdown` after **6b** is a harmless no-op check that it is closed (`is_open:false`).

## 7. Base port, Save and Fit view

**7a. Advance to the port page** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Next", "text":"Next"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Next"}`
→ `{"ok":true,"kind":"button","text":"Next"}`
(shows `"<N> pipeline(s) configured."` and the field `"Base port (each pipeline gets base_port + its index)"`, default `8001`).

**7b. Keep the default base port `<P>`**, then **Save** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`

**7c. Fit view** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"fit view", "text":"Fit view"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"fit view"}`
→ `{"ok":true,"kind":"button","text":""}`

**Verification**: `GET /_agent/notifications` → `"Generated <N> (V/L)LM pipeline(s)"`; `GET /_agent/graph` → `3×<N>` nodes (`input-<i>`, `vllm-<i>`, `sink-<i>`) and `2×<N>` edges, with `vllm-<i>` data `"port": <P>+<i>-1`, `"devices": ["metis-<bus>"]` and `"artifact"` ending `<M>/axscript`; screenshot shows `<N>` Input → (V/L)LM → Sink chains.

**Notes**: if `get_graph` is empty after Save although `Generated ...` was notified, stop and report it; do not repeat the wizard blindly.

## 8. Compile and launch

**8a. Baseline notifications** — `GET /_agent/notifications`, record the current max `id`.

**8b. Click the button** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Compile and Launch Pipeline", "text":"Compile and Launch"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Compile and Launch Pipeline"}`
→ `{"ok":true,"kind":"button","text":"buildCompile and Launch Pipeline"}`

**Verification**: poll `GET /_agent/notifications` with `since_id=<baseline>` → `"Launched <N> vLLM VLM server(s): vllm-1 (port <P>), ..., vllm-<N> (port <P>+<N>-1)"` (`"type":"positive"`).

**Notes**: there is no YAML step for (V/L)LM pipelines. A click on a disabled button returns `{"ok":false,"error":"not_found"}`; the button is enabled only while the canvas holds nodes.

## 9. Open the Benchmarking tab and set the stat toggles

**9a. Switch tabs** — `POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Benchmarking", "text":"Benchmarking tab"}`
→ `{"ok":true,"id":"<anno-id>","kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Benchmarking"}`
→ `{"ok":true,"kind":"tab","text":"Benchmarking"}`

**9b. Open the settings drawer** — `POST /_agent/highlight` `{"client_id", "kind":"edge", "target":"benchmark settings edge", "text":"Open settings drawer"}` → `{"ok":true,"id":"<anno-id>","kind":"edge","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/hover` `{"client_id", "text":"benchmark settings edge", "action":"enter"}` → `{"ok":true,"text":""}`

**9c. Set the toggles** — for each (`Per-source latency`,`false`), (`CPU utilization`,`true`), (`Memory utilization`,`true`), (`Aggregate core utilization %`,`true`), (`Aggregate MVM utilization %`,`true`), (`Aggregate DDR utilization %`,`true`):
`POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"<label>", "text":"<label> <value>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"<label>", "value":"<value>"}`
→ `{"ok":true,"kind":"toggle","changed":true}`

**9d. Close the drawer** — `POST /_agent/highlight` `{"client_id", "kind":"auto", "target":"benchmark settings drawer", "text":"Close drawer"}` → `{"ok":true,...}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/hover` `{"client_id", "text":"benchmark settings drawer", "action":"leave"}` → `{"ok":true,"text":"Advanced SettingsInference endpoint(s)Pipeline ID(s) for bac"}`

**Verification**: `GET /_agent/state` → each toggle's `"checked"` matches **9c**, then `"drawer":{"open":false,...}`. Open the (V/L)LM server dropdown (`toggle_dropdown` label `(V/L)LM server`, then `read_dropdown_options`, then `toggle_dropdown` again to close) → `<N>` options `vllm-<i> (1 instance, port(s) <P>+<i>-1)`.

**Notes**: a fresh browser session starts with `Per-source latency` on and the utilization toggles off, so check them rather than assuming. `hover` takes `text` (not `target`) and `action`. The (V/L)LM Chat panel is unique per server: a chat or loop on `vllm-1` is invisible on `vllm-2`.

## 10. Build the prompt library

**10a. Open the library** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"add", "text":"Add a prompt to your library"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"add"}`
→ `{"ok":true,"kind":"button","text":"add"}`
(opens the "Prompt library" dialog: one row per saved prompt with a checkbox and a delete icon, `Prompt text`, `Add image(s)`, `Close`, `Save`, `Add Prompt`).

**10b. Delete every existing prompt** — for each existing title `<old>`:
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Delete prompt: <old>", "text":"Delete <old>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Delete prompt: <old>"}`
→ `{"ok":true,"kind":"button","text":"delete"}`

**10c. Add a text prompt `<T1>`** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Prompt text", "text":"Prompt text"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Prompt text", "value":"<T1>"}`
→ `{"ok":true,"kind":"input"}`
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add Prompt", "text":"Add Prompt"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Add Prompt"}`
→ `{"ok":true,"kind":"button","text":"Add Prompt"}`

**10d. Add an image prompt `<T2>`** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add image(s)", "text":"Add image(s)"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Add image(s)"}`
→ `{"ok":true,"kind":"button","text":"add_photo_alternateAdd image(s)"}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"File / folder dropdown"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/toggle_dropdown` `{"client_id", "label":"File / folder"}`
→ `{"ok":true,"action":"opened|closed","is_open":true|false}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File / folder", "text":"<image>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"File / folder", "value":"<image>"}`
→ `{"ok":true,"kind":"select","text":"<image>"}`
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add", "text":"Add image"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Add"}`
→ `{"ok":true,"kind":"button","text":"Add"}`
`POST /_agent/highlight` `{"client_id", "kind":"field", "target":"Prompt text", "text":"Prompt text"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"Prompt text", "value":"<T2>"}`
→ `{"ok":true,"kind":"input"}`
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Add Prompt", "text":"Add Prompt"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Add Prompt"}`
→ `{"ok":true,"kind":"button","text":"Add Prompt"}`

**10e. Tick both prompts** — for each row label `<title-as-listed>` (its truncated title followed by `delete`, e.g. `Describe what the people in this... (1 image)delete`):
`POST /_agent/highlight` `{"client_id", "kind":"toggle", "target":"<row label>", "text":"Tick <title>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"toggle","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"<row label>"}`
→ `{"ok":true,"kind":"toggle","text":""}`

**10f. Save and close** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`
`POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Close", "text":"Close"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Close"}`
→ `{"ok":true,"kind":"button","text":"Close"}`

**Verification**: before **10f**, `GET /_agent/state` → both rows `"checked":true`; after Save, `GET /_agent/notifications` → `"Prompt checkbox states saved"`; after Close, `"dialog_open":false`.

**Notes**:
- The delete buttons carry the aria-label `Delete prompt: <title>`, so **10b** disambiguates by title; bare `delete` is ambiguous with several rows.
- Ticking is by `click`, not `set_field` (`set_field` returns `not_found` for these rows). If the title is also a substring of its own delete button's label, `click` reports `ambiguous`; use the full row label (title plus `delete`).
- Saving with both rows unticked stores nothing to play: always verify `"checked":true` before **10f**.
- Image prompts count as `(1 image)` in the listed title. The library is shared by all servers.

## 11. Play the library against each server

Repeat **11a–11b** for `<i>` = 1 .. `<N>`.

**11a. Select the server** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"(V/L)LM server", "text":"Select <S_i>"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"(V/L)LM server", "value":"vllm-<i> (1 instance, port(s) <P>+<i>-1)"}`
→ `{"ok":true,"kind":"select","text":"vllm-<i> (1 instance, port(s) <P>+<i>-1)"}`

**11b. Press Play** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Loop selected prompts", "text":"Loop selected prompts (<S_i>)"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Loop selected prompts"}`
→ `{"ok":true,"kind":"button","text":"play_arrow"}`

**Verification**: screenshot — the Play button turns into a red stop button and the chat shows `[vllm-<i>, prompt k/2 · TTFT <t>s · <r> tok/s] <reply>`.

**Notes**: the Play button's aria-label is `Loop selected prompts` in both states (bare `play_arrow` is ambiguous with the palette's tree icons). Each server runs its own loop, independently of whichever server is displayed.

## 12. Verify load

**12a. Replies** — for each `<i>`, select `<S_i>` (as **11a**) and screenshot (`max_width=1280`, `quality=0.5`).

**12b. Utilization** — screenshot the plot.

**Verification**: every server shows replies labelled `prompt k/2` with an average line `avg (last <n>): TTFT <t>s · <r> tok/s`; the CPU series rises well above the pre-loop baseline while the loops run. The aggregate core, MVM and DDR series appear only if the device answers the monitor tool; their absence is acceptable.

**Notes**: record the baseline CPU level in a screenshot **before 11b** to compare against.

## 13. Stop the loops and clear the chats

**13a. Stop each loop** — for `<i>` = 1 .. `<N>`: select `<S_i>` (**11a**), then `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Loop selected prompts", "text":"Stop loop (<S_i>)"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Loop selected prompts"}`
→ `{"ok":true,"kind":"button","text":"stop"}`

**13b. Clear each chat** — for `<i>` = 1 .. `<N>`: select `<S_i>`, then `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Clear", "text":"Clear chat (<S_i>)"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Clear"}`
→ `{"ok":true,"kind":"button","text":"Clear"}`

**Verification**: after **13a** the Play button is back to the play icon and, after about a minute, the CPU series returns to the pre-loop baseline; after **13b** the chat area is empty (screenshot).

**Notes**: a reply already in flight may still arrive after Stop; clear after it lands.

## 14. Teardown

**14a.** Switch to the Pipeline Editor tab — `POST /_agent/highlight` `{"client_id", "kind":"tab", "target":"Pipeline Editor", "text":"Pipeline Editor tab"}`
→ `{"ok":true,"id":"<anno-id>","kind":"tab","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Pipeline Editor"}`
→ `{"ok":true,"kind":"tab","text":"Pipeline Editor"}`

**14b.** Repeat **2** (Force Stop All with confirmation) and **3** (Clear canvas with confirmation).

**Verification**: `GET /_agent/notifications` → `"Stopped <N> vLLM/LLM server(s): vllm-1, ..., vllm-<N>"`; `GET /_agent/graph` → `{"nodes":[],"edges":[]}`.

**Notes**: Force Stop All ends the run for every (V/L)LM server on the host, including ones other sessions launched.
