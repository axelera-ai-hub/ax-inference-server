"""Static node-catalog data for the Pipeline Editor: palette tree, per-node default data and the demo canvas.

Exposes `PALETTE_TREE`, `NODE_CATALOG`, `DEMO_NODES`, `DEMO_EDGES` and the default constants used by the graph, dialog and wizard modules.
"""


# AI cores per device; the denominator of the "cores free" counts shown in the dialogs.
CORES_PER_DEVICE = 4

# Placeholder axnet path for a model slot that has not been configured yet (Vision node, ROI model A/B).
UNCONFIGURED_AXNET = '${SDK_ROOT}/build/MODEL/MODEL.axnet'

# Placeholder artifact directory for a (V/L)LM node that has not been configured yet.
UNCONFIGURED_VLLM_ARTIFACT = '${SDK_ROOT}/build/MODEL/axscript'

# Server-side defaults for the image-decode queue. Used when loading a config that omits the fields and
# to decide whether a value must be written back out (see `pipeline_graph.py`).
# These differ from the GUI defaults below, which are pre-filled for new pipelines.
_SERVER_IMDECODE_QUEUE_DEPTH_DEFAULT = 1
_SERVER_IMDECODE_QUEUE_TIMEOUT_MS_DEFAULT = 2000

# GUI defaults pre-filled for the image-decode settings of new Input nodes and the example wizards.
DEFAULT_IMDECODE_THREADS = 4
DEFAULT_IMDECODE_QUEUE_DEPTH = 32
DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS = 20000

# Initial canvas: input -> vision net (yolox-m-coco-onnx) -> sink. Note the net node has no explicit `type`.
DEMO_NODES = [
    {
        'id': 'input-1',
        'type': 'input',
        'position': {'x': 50, 'y': 100},
        'data': {
            'label': 'input', 'kind': 'input', 'port': 50060, 'pipeline_id': 'iso-detect',
            'timeout': 60, 'watchdog_timeout_ms': 0, 'result_queue_depth': None,
            'taskset_cpus': None, 'membind': None,
            'imdecode_threads': DEFAULT_IMDECODE_THREADS,
            'imdecode_queue_depth': DEFAULT_IMDECODE_QUEUE_DEPTH,
            'imdecode_queue_timeout_ms': DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS,
        },
    },
    {
        'id': 'net-1',
        'position': {'x': 250, 'y': 100},
        'data': {
            'label': 'net: yolox-m-coco-onnx',
            'kind': 'vision',
            'axnet': '${SDK_ROOT}/build/yolox-m-coco-onnx/yolox-m-coco-onnx.axnet',
            'device': 0,
            'cores': 4,
        },
    },
    {
        'id': 'sink-1',
        'type': 'output',
        'position': {'x': 450, 'y': 100},
        'data': {
            'label': 'sink',
            'kind': 'sink',
            'im_decode_output_format': 'I420',
        },
    },
]
DEMO_EDGES = [
    {'id': 'input-1->net-1', 'source': 'input-1', 'target': 'net-1'},
    {'id': 'net-1->sink-1', 'source': 'net-1', 'target': 'sink-1'},
]

# Tree shown in the node palette. Leaf ids are the keys of NODE_CATALOG (node leaves) or the
# `example-*` wizard ids.
PALETTE_TREE = [
    {
        'id': 'nodes', 'label': 'Nodes',
        'children': [
            {
                'id': 'sources', 'label': 'Sources', 'icon': 'input',
                'children': [
                    {'id': 'source-input', 'label': 'Input', 'icon': 'login'},
                ],
            },
            {
                'id': 'models', 'label': 'Models', 'icon': 'widgets',
                'children': [
                    {'id': 'model-vision', 'label': 'Vision', 'icon': 'visibility'},
                    {'id': 'model-vllm-vlm', 'label': '(V/L)LM', 'icon': 'image_search'},
                    {'id': 'model-filter', 'label': 'Filter', 'icon': 'filter_alt'},
                    {'id': 'model-roi', 'label': 'ROI', 'icon': 'crop_free'},
                ],
            },
            {
                'id': 'sinks', 'label': 'Sinks', 'icon': 'output',
                'children': [
                    {'id': 'sink-output', 'label': 'Sink', 'icon': 'logout'},
                ],
            },
        ],
    },
    {
        'id': 'examples', 'label': 'Examples',
        'children': [
            {'id': 'example-isovision', 'label': 'Isovision Demo', 'icon': 'science'},
            {'id': 'example-two-stage-cascade', 'label': 'Two-Stage Cascade', 'icon': 'science'},
            {'id': 'example-three-stage-cascade', 'label': 'Three-Stage Conditional Cascade', 'icon': 'science'},
            {'id': 'example-iso-vllm-demo', 'label': 'Iso-VLM/LLM-Demo', 'icon': 'science'},
        ],
    },
]

# Default `flush_thres` of the Input node; the value is written to the config only when it differs.
DEFAULT_FLUSH_THRES = 4850

# Default per-model queue depth and timeout (ms) for Vision and ROI model slots.
DEFAULT_MODEL_QUEUE_DEPTH = 64
DEFAULT_MODEL_QUEUE_TIMEOUT_MS = 2000

# Default node definitions by palette leaf id: display label, optional canvas `type`, and the initial
# `data` payload copied into a new node. 'model-track' has no palette entry.
NODE_CATALOG = {
    'source-input': {
        'label': 'Input', 'type': 'input',
        'data': {
            'kind': 'input', 'port': 50060, 'pipeline_id': '',
            'timeout': 60, 'watchdog_timeout_ms': 0, 'result_queue_depth': None,
            'taskset_cpus': None,
            'membind': None,
            'imdecode_threads': DEFAULT_IMDECODE_THREADS,
            'imdecode_queue_depth': DEFAULT_IMDECODE_QUEUE_DEPTH,
            'imdecode_queue_timeout_ms': DEFAULT_IMDECODE_QUEUE_TIMEOUT_MS,
            'flush_thres': DEFAULT_FLUSH_THRES,
        },
    },
    'model-vision': {
        'label': 'Vision',
        'data': {
            'kind': 'vision',
            'net_name': None,
            'axnet': UNCONFIGURED_AXNET,
            'device': 0,
            'cores': 4,
            'labels_file': None,
            'meta_key_override': None,
            'queue_depth': DEFAULT_MODEL_QUEUE_DEPTH,
            'queue_timeout_ms': DEFAULT_MODEL_QUEUE_TIMEOUT_MS,
        },
    },
    'model-vllm-vlm': {
        'label': '(V/L)LM',
        'data': {
            'kind': 'vllm_vlm',
            'artifact': UNCONFIGURED_VLLM_ARTIFACT,
            'devices': [],
            'port': 8001,
            'enable_thinking': False,
            'temperature': 0.0,
            'is_vlm': False,
            'resize_width': 512,
            'resize_height': 512,
        },
    },
    'model-track': {'label': 'Track', 'data': {'kind': 'track'}},
    'model-filter': {
        'label': 'Filter',
        'data': {
            'kind': 'filter',
            'meta_key': 'detections',
            'classes': None,
            'min_score': None,
            'max_score': None,
            'min_width': None,
            'min_height': None,
            'top_k': None,
            'which': 'all',
        },
    },
    'model-roi': {
        'label': 'ROI',
        'data': {
            'kind': 'roi',
            'det_meta_key': 'detections',
            'crop_padding': 0.0,
            'max_iters': 50,
            'dispatch_queue_depth': None,
            'mode': 'simple',
            'model_a': {
                'net_name': None,
                'axnet': UNCONFIGURED_AXNET,
                'device': 0,
                'cores': 4,
                'labels_file': None,
                'meta_key_override': None,
                'queue_depth': DEFAULT_MODEL_QUEUE_DEPTH,
                'queue_timeout_ms': DEFAULT_MODEL_QUEUE_TIMEOUT_MS,
                'cls_meta_key': 'keypoint_detections',
            },
            'model_b': {
                'net_name': None,
                'axnet': UNCONFIGURED_AXNET,
                'device': 0,
                'cores': 4,
                'labels_file': None,
                'meta_key_override': None,
                'queue_depth': DEFAULT_MODEL_QUEUE_DEPTH,
                'queue_timeout_ms': DEFAULT_MODEL_QUEUE_TIMEOUT_MS,
                'cls_meta_key': 'face_detections',
            },
            'predicate': {
                'name': 'roi_gate',
                'type': 'meta_key_exists',
                'meta_key': None,
                'indices': None,
                'value': None,
                'inputs_json': None,
                'body': None,
            },
        },
    },
    'sink-output': {
        'label': 'Sink',
        'type': 'output',
        'data': {
            'kind': 'sink',
        },
    },
}
