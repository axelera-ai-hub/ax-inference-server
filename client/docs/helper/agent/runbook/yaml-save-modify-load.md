# YAML Save, Modify and Load

Runbook for changing a pipeline layout the wizards cannot express: save the
canvas as a YAML, hand-edit a copy on the host, load the copy back through
**Load Config**, and launch it. Same host and conventions as the other
sections. Run it on a host where the server container and the GUI are up.

Files involved (`<repo>` is the repository root on the host):

- Generated and hand-made configs: `<repo>/client/ui/gui/generated_configs/<name>.yaml`
- Compiled pipeline specs: `<repo>/.sdk/voyager-sdk/pipeline_specs/<name>/pipeline_<N>.json`
  (written by Compile and Launch; the directory name can differ from the YAML name)

---

## 1. Confirm the target session

`GET /_agent/sessions`
→ `{"sessions":[{"client_id":"<client_id>","has_socket_connection":true}]}`

**Verification**: response body itself — confirms `<client_id>` is
connected and is the only session.

**Notes**: if a later call returns `{"detail":"no connected client with id
'<client_id>'"}`, the browser page reconnected under a new `client_id`;
repeat this sub-section and redo the interrupted step. Keep the GUI browser
tab in the foreground for the whole run: in a background tab the
dropdowns in §5 do not open.

## 2. Generate and save a config

**2a. Open the YAML dialog** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Generate Config YAML", "text":"Generate Config YAML"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Generate Config YAML"}`
→ `{"ok":true,"kind":"button","text":"boltGenerate Config YAML"}`

**2b. Name the file** — `POST /_agent/highlight` `{"client_id", "kind":"field", "target":"File name", "text":"File name"}`
→ `{"ok":true,"id":"<anno-id>","kind":"field","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/set_field` `{"client_id", "label":"File name", "value":"<name>"}`
→ `{"ok":true,"kind":"input"}`

**2c. Save** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Save", "text":"Save"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Save"}`
→ `{"ok":true,"kind":"button","text":"Save"}`

**Verification**: `GET /_agent/notifications` with `since_id=<max id recorded before 2a>` — `Wrote <repo>/client/ui/gui/generated_configs/<name>.yaml`.

**Notes**: use a new `<name>` for every save so earlier configs are kept. The name appears in the Load Config list, so describe the layout and tuning in it (for example `<model>_<N>dev_<cores>_<decode>`).

## 3. Edit a copy of the YAML on the host

`cp <repo>/client/ui/gui/generated_configs/<name>.yaml <repo>/client/ui/gui/generated_configs/<new_name>.yaml`
`sed -i 's/imdecode_threads: <old>/imdecode_threads: <new>/g' <repo>/client/ui/gui/generated_configs/<new_name>.yaml`
`diff <repo>/client/ui/gui/generated_configs/<name>.yaml <repo>/client/ui/gui/generated_configs/<new_name>.yaml`

**Verification**: the `diff` shows only the intended lines.

**Notes**: edit the copy and keep the original. The fields that matter for tuning:

- `global:` → `use_axinference_net_opencl: --enable-opencl` or `--disable-opencl`.
- `nets:` → `<net>:` → `axnet_config: net-0;devices:<device>-<cores>`. A net spanning several devices lists one `net-N;devices:` entry per device, `;`-separated.
- `pipelines:` → `taskset_cpus` (CPUs the pipeline is pinned to, covering decode and pre/post-processing), `imdecode_threads`, `port` (one per pipeline, counting up from the first) and `id`.
- To run fewer pipelines, delete both the pipeline entry and its net entry; to add one, copy both and give the pipeline a new `port`.

## 4. Stop what is running on the target ports

Stop any running pipelines and remove all sources first: repeat §16 and then §2 of [examples-iso-vision-demo.md](examples-iso-vision-demo.md) (sources removed on the Benchmarking tab, then Force Stop All on the Pipeline Editor tab).

**Verification**: `<host>` shell `pgrep -af axinferencenet_grpc` prints no pipeline process.

**Notes**: Force Stop All signals every `axinferencenet_grpc` process on the machine, including other users'; on a shared host, check the process list and who owns each process before confirming. Loading a config changes only the canvas and never touches running pipelines, so a running pipeline holds its ports until it is stopped.

## 5. Load the YAML through Load Config

**5a. Open the dialog** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Load Config", "text":"Load Config"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Load Config"}`
→ `{"ok":true,"kind":"button","text":"folder_openLoad Config"}`

**5b. Open the Config file dropdown** — `POST /_agent/toggle_dropdown` `{"client_id", "label":"Config file"}`
→ `{"ok":true,"action":"opened","is_open":true}`
`POST /_agent/read_dropdown_options` `{"client_id", "label":"Config file"}`
→ `{"ok":true,"options":[...,{"text":"<new_name>.yaml","selected":false},...]}`

**5c. Select the file** — `POST /_agent/set_field` `{"client_id", "label":"Config file", "value":"<new_name>.yaml"}`
→ `{"ok":true,"kind":"select","text":"<new_name>.yaml"}`
`GET /_agent/state` with `client_id` — the dialog's `"Config file"` field must read `"<new_name>.yaml"`.

**5d. Load** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Load", "text":"Load"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Load"}`
→ `{"ok":true,"kind":"button","text":"Load"}`

**Verification**: `GET /_agent/notifications` with `since_id=<max id recorded before 5a>` — `Loaded <new_name>.yaml`, with exactly the name selected in 5c.

**Notes**:

- **5b**: if the toggle reports `"is_open":false` or the read returns `{"ok":false,"error":"not_open"}`, the page is usually in a background tab; bring it to the foreground, close and reopen the dialog, and toggle again.
- **5c**: the dropdown holds the first file in the list (`cascade-demo.yaml` on a fresh host) until a file is selected, and `set_field` can return `ok` without changing it. Never click Load until the `GET /_agent/state` read shows the intended name; loading the wrong file replaces the canvas with it.
- **5d**: loading replaces the canvas with the file's pipelines.

## 6. Verify the loaded canvas

`GET /_agent/graph` with `client_id`
→ `{"nodes":[{"id":"input-<N>","type":"input","data":{"port":<port>,"taskset_cpus":"<cpus>","imdecode_threads":<n>,...}},{"id":"<net>","data":{"device_cores":[{"device":<device>,"cores":<cores>}]}},{"id":"sink-<N>","type":"output"}],"edges":[...]}`

**Verification**: one Input → net → Sink chain per pipeline in the file; every Input node's `taskset_cpus`, `imdecode_threads` and `port`, and every net node's `device_cores`, match the edited YAML.

## 7. Save the loaded canvas under a new name

Repeat §2 with `<run_name>` (Generate Config YAML, `File name`, Save), then:

`diff <repo>/client/ui/gui/generated_configs/<new_name>.yaml <repo>/client/ui/gui/generated_configs/<run_name>.yaml`

**Verification**: `Wrote .../<run_name>.yaml`; the `diff` is empty or lists only fields the GUI adds.

**Notes**: Compile and Launch Pipeline stays disabled until a YAML has been generated and saved. The GUI can add fields the source file lacks (for example `flush_thres` on Input nodes), so read the diff before relying on the file.

## 8. Compile and launch, then verify on the host

**8a. Click Compile and Launch** — `POST /_agent/highlight` `{"client_id", "kind":"button", "target":"Compile and Launch Pipeline", "text":"Compile and Launch"}`
→ `{"ok":true,"id":"<anno-id>","kind":"button","rect":{...}}`
`POST /_agent/clear_highlight` `{"client_id"}` → `{"ok":true}`
`POST /_agent/click` `{"client_id", "text":"Compile and Launch"}`
→ `{"ok":true,"kind":"button","text":"buildCompile and Launch Pipeline"}`

**8b. Check the processes** — `pgrep -af axinferencenet_grpc`
`taskset -cp <pid>`

**Verification**: `GET /_agent/notifications` — `Compiled <H> pipeline spec(s) ...` then `Launched <H> pipeline(s)`; `pgrep` shows `<H>` pipeline processes with `--port <port>` and `--imdecode-threads <n>` as in the YAML, and `taskset -cp` reports each process's `taskset_cpus`.

**Notes**: a click on a disabled Compile button returns `ok` and does nothing; poll `GET /_agent/state` until the button reads `"disabled":false`. The `pgrep` command also lists its own shell on some hosts; count only the pipeline processes. To benchmark the launched layout, follow "Benchmarking Vision Pipelines" ([benchmarking-vision.md](benchmarking-vision.md)) and the tuning section of [examples-iso-vision-demo.md](examples-iso-vision-demo.md).
