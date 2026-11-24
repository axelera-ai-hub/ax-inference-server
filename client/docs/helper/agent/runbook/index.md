# FastAPI Runbook — Index

Call-by-call runbooks for driving the Pipeline Editor GUI through its
`/_agent/*` routes (executed as the equivalent MCP tools; see the skill in
`../.claude/skills/inference-server-agent/SKILL.md`). Each topic is its own
file. Read [document-format.md](document-format.md) first: it defines the
conventions every other file follows.

| Topic | File | What it covers | Prerequisite |
|---|---|---|---|
| Document Format | [document-format.md](document-format.md) | Layout, call/response notation, Verification/Notes rules | — |
| Vision Demo: Single Pipeline | [vision-demo.md](vision-demo.md) | Build Input → Vision → Sink by hand, configure, generate YAML, compile and launch | — |
| VLM Demo | [vlm-demo.md](vlm-demo.md) | Build Input → (V/L)LM → Sink, configure artifact, device and generation settings, launch | — |
| Benchmarking Vision Pipelines | [benchmarking-vision.md](benchmarking-vision.md) | Benchmarking tab: drawer, stat toggles, file sources, plot, teardown | A launched Vision pipeline (Vision Demo or ISO Vision Demo) |
| Benchmarking VLMs and LLMs | [benchmarking-vlm-llm.md](benchmarking-vlm-llm.md) | Chat panel: endpoint check, text and image prompts, teardown | A launched (V/L)LM server (VLM Demo) |
| Examples: ISO Vision Demo | [examples-iso-vision-demo.md](examples-iso-vision-demo.md) | Palette Examples wizard: health check, throughput gate, multi-device pipelines, launch, benchmark within the gate and overload, tune the layout and measure the aggregate FPS | — |
| Examples: Two-Stage Cascade | [examples-two-stage-cascade.md](examples-two-stage-cascade.md) | Palette Examples wizard: detection model + pose model sharing one device, per-model cores, health check, YAML check, launch, one-source benchmark, cleanup | — |
| Examples: Three-Stage Conditional Cascade | [examples-three-stage-conditional-cascade.md](examples-three-stage-conditional-cascade.md) | Palette Examples wizard: detection → pose → gated face model sharing one device, per-model cores, keypoint-confidence gate, health check, YAML check, launch, 25 FPS one-source benchmark, cleanup | — |
| Examples: Iso-VLM/LLM-Demo | [examples-iso-vlm-llm-demo.md](examples-iso-vlm-llm-demo.md) | Palette Examples wizard: N parallel (V/L)LM pipelines, device health check first, per-pipeline model/device/settings, launch, prompt-library loop benchmark on every server, cleanup | — |
| YAML Save, Modify and Load | [yaml-save-modify-load.md](yaml-save-modify-load.md) | Save the canvas as a YAML, hand-edit a copy on the host, load it through Load Config, verify the canvas, save, compile and launch, check processes and CPU pinning | A running GUI session (ISO Vision Demo for a typical layout) |
