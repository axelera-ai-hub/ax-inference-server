"""Chat tab logic for talking to running (V/L)LM servers launched from the Pipeline Editor.

Holds per-server chat sessions, the prompt library (JSONL on disk), prompt replay, token-budget estimation and streaming of responses.

Note:
    The widgets are created in `app.py` and handed over once through `configure()`; the handlers here use them as module globals.
"""


import asyncio
import base64
import functools
import json
import math
import mimetypes
import os
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import httpx
from nicegui import ui

from benchmark import _benchmark_list_dir
from inference.llm_vlm import AsyncAxLlmClient, AsyncAxVlmClient
from pipeline_graph import _node_by_id

# Prompt library file and its image folder live under generated_configs/.
GENERATED_CONFIGS_DIR = os.path.join(os.path.dirname(__file__), 'generated_configs')
PROMPT_LIBRARY_PATH = os.path.join(GENERATED_CONFIGS_DIR, 'prompt_library.jsonl')
PROMPT_LIBRARY_IMAGES_DIR = os.path.join(GENERATED_CONFIGS_DIR, 'prompt_library_images')

# Folder the image picker opens in, when it exists.
BENCHMARK_SOURCE_DEFAULT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'test_images'))
BENCHMARK_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp'}
# Maximum images per message or library prompt.
CHAT_MAX_IMAGES = 8
# Seconds without edits before the token estimate is recomputed.
CHAT_TOKEN_DEBOUNCE_S = 1.2
# Number of recent requests averaged in the metrics label.
CHAT_METRICS_HISTORY_MAXLEN = 10
# Estimated image tokens = ceil(width/28) * ceil(height/28).
CHAT_VISION_TOKEN_PATCH_PX = 28

# Host server used to list running (V/L)LM instances; empty means not configured.
HOST_SERVER_URL = os.environ.get('HOST_SERVER_URL', '').rstrip('/')
HOST_SERVER_API_KEY = os.environ.get('HOST_SERVER_API_KEY', '')

# Widgets assigned by configure().
chat_endpoint_select = None
chat_max_tokens_input = None
chat_concurrency_input = None
chat_log = None
play_btn = None
send_btn = None
chat_images_label = None
chat_images_row = None
chat_text_input = None
chat_budget_label = None
chat_metrics_label = None


def configure(
    *, chat_endpoint_select_, chat_max_tokens_input_, chat_concurrency_input_,
    chat_log_, play_btn_, send_btn_, chat_images_label_, chat_images_row_,
    chat_text_input_, chat_budget_label_, chat_metrics_label_,
) -> None:
    """Store the chat widgets created by the UI so the handlers in this module can use them.

    Args:
        chat_endpoint_select_: Dropdown listing running (V/L)LM server groups.
        chat_max_tokens_input_: Number input for max new tokens.
        chat_concurrency_input_: Number input for concurrent requests.
        chat_log_: Scroll area holding the message bubbles.
        play_btn_: Prompt-library replay button.
        send_btn_: Send button.
        chat_images_label_: Label showing the attached-image count.
        chat_images_row_: Row holding the attached-image thumbnails.
        chat_text_input_: Message textarea.
        chat_budget_label_: Label showing the token estimate.
        chat_metrics_label_: Label showing average TTFT and tokens/s.
    """
    global chat_endpoint_select, chat_max_tokens_input, chat_concurrency_input
    global chat_log, play_btn, send_btn, chat_images_label, chat_images_row
    global chat_text_input, chat_budget_label, chat_metrics_label
    chat_endpoint_select = chat_endpoint_select_
    chat_max_tokens_input = chat_max_tokens_input_
    chat_concurrency_input = chat_concurrency_input_
    chat_log = chat_log_
    play_btn = play_btn_
    send_btn = send_btn_
    chat_images_label = chat_images_label_
    chat_images_row = chat_images_row_
    chat_text_input = chat_text_input_
    chat_budget_label = chat_budget_label_
    chat_metrics_label = chat_metrics_label_


# Running instances by node id, filled by _chat_refresh_groups.
_chat_groups: dict[str, list[dict]] = {}

# Chat state by node id (see _get_chat_session).
_chat_sessions: dict[str, dict] = {}

# Node id whose session is currently shown.
_chat_active_node_id: str | None = None

# Text labels of in-progress bubbles of the active session, by message index.
_active_message_labels: dict[int, object] = {}


def _get_chat_session(node_id: str) -> dict:
    """Return the chat session for a server group, creating it on first use.

    A session is a dict with `messages`, `pending_images`, `draft_text`, `playing`, `play_task`, `metrics` (bounded deque of (ttft, tok/s)), `last_edit_ts`, `last_counted_key` and `busy`.

    Args:
        node_id (str): Id of the (V/L)LM node that owns the server instances.
    """
    session = _chat_sessions.get(node_id)
    if session is None:
        session = {
            'messages': [],
            'pending_images': [],
            'draft_text': '',
            'playing': False,
            'play_task': None,
            'metrics': deque(maxlen=CHAT_METRICS_HISTORY_MAXLEN),
            'last_edit_ts': 0.0,
            'last_counted_key': None,
            'busy': False,
        }
        _chat_sessions[node_id] = session
    return session


def _chat_instance_base_url(port: int) -> str:
    """Build the HTTP base URL of a (V/L)LM instance from the host server's hostname and the instance port."""
    host = urlparse(HOST_SERVER_URL).hostname or '127.0.0.1'
    return f'http://{host}:{port}'


async def _chat_refresh_groups() -> None:
    """Query the host server for running (V/L)LM instances and refresh the endpoint dropdown.

    Instances are grouped by the node id (the part of the instance name before `__`). Keeps the current selection when it is still available, otherwise selects the first group, and activates that session. Notifies instead of raising on errors.
    """
    if not HOST_SERVER_URL:
        ui.notify('HOST_SERVER_URL is not configured on this GUI instance', type='warning')
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f'{HOST_SERVER_URL}/api/v1/vllm/status', headers={'X-API-Key': HOST_SERVER_API_KEY},
            )
            resp.raise_for_status()
            instances = resp.json()['instances']
    except Exception as exc:
        ui.notify(f'failed to list running (V/L)LM servers: {exc}', type='negative')
        return
    groups: dict[str, list[dict]] = {}
    for inst in instances:
        if not inst.get('running'):
            continue
        node_id = inst['name'].split('__', 1)[0]
        groups.setdefault(node_id, []).append(inst)
    _chat_groups.clear()
    _chat_groups.update(groups)
    options = {
        node_id: f"{node_id} ({len(insts)} instance{'s' if len(insts) != 1 else ''}, "
                 f"port(s) {', '.join(str(i['port']) for i in insts)})"
        for node_id, insts in groups.items()
    }
    current = chat_endpoint_select.value
    new_value = current if current in options else next(iter(options), None)
    chat_endpoint_select.set_options(options, value=new_value)
    if new_value != _chat_active_node_id:
        _chat_activate_session(new_value)
    if not options:
        ui.notify('no running (V/L)LM servers found -- launch one from the Pipeline Editor tab first', type='info')


def _prompt_library_load() -> list[dict]:
    """Read the prompt library JSONL file, skipping blank and malformed lines. Returns an empty list if the file does not exist."""
    if not os.path.exists(PROMPT_LIBRARY_PATH):
        return []
    entries = []
    with open(PROMPT_LIBRARY_PATH, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _prompt_library_save(entries: list[dict]) -> None:
    """Write all prompt library entries to the JSONL file via a temporary file and atomic replace."""
    os.makedirs(GENERATED_CONFIGS_DIR, exist_ok=True)
    tmp_path = PROMPT_LIBRARY_PATH + '.tmp'
    with open(tmp_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')
    os.replace(tmp_path, PROMPT_LIBRARY_PATH)


def _prompt_library_title(text: str, num_images: int) -> str:
    """Build a display title from the first six words of the prompt, or an "Untitled" label when the text is empty."""
    words = (text or '').split()
    if words:
        title = ' '.join(words[:6])
        return title + ('...' if len(words) > 6 else '')
    if num_images:
        return f"Untitled ({num_images} image{'s' if num_images != 1 else ''})"
    return 'Untitled prompt'


def _prompt_library_add(text: str, images: list[dict]) -> dict:
    """Save a new prompt, with its images written to disk, to the prompt library.

    Args:
        text (str): Prompt text.
        images (list[dict]): Images as dicts with `bytes`, `mime` and optionally `name`.

    Returns:
        dict: The stored entry (`id`, `title`, `text`, `image_paths`, `checked`, `created_at`).
    """
    os.makedirs(PROMPT_LIBRARY_IMAGES_DIR, exist_ok=True)
    entry_id = uuid.uuid4().hex
    image_paths = []
    for idx, img in enumerate(images):
        ext = mimetypes.guess_extension(img['mime']) or os.path.splitext(img.get('name', ''))[1] or '.bin'
        out_name = f"{entry_id}_{idx}{ext}"
        out_path = os.path.join(PROMPT_LIBRARY_IMAGES_DIR, out_name)
        with open(out_path, 'wb') as f:
            f.write(img['bytes'])
        image_paths.append(out_path)
    entry = {
        'id': entry_id,
        'title': _prompt_library_title(text, len(images)),
        'text': text,
        'image_paths': image_paths,
        'checked': False,
        'created_at': time.time(),
    }
    entries = _prompt_library_load()
    entries.append(entry)
    _prompt_library_save(entries)
    return entry


def _prompt_library_delete(entry_id: str) -> None:
    """Remove a prompt library entry and delete its image files."""
    entries = _prompt_library_load()
    keep, drop = [], []
    for entry in entries:
        (drop if entry['id'] == entry_id else keep).append(entry)
    for entry in drop:
        for path in entry.get('image_paths') or []:
            try:
                os.remove(path)
            except OSError:
                pass
    _prompt_library_save(keep)


def _chat_render_images(node_id: str | None) -> None:
    """Redraw the attached-image thumbnails and count label, but only when `node_id` is the active session."""
    if node_id != _chat_active_node_id:
        return
    images = _chat_sessions[node_id]['pending_images'] if node_id else []
    chat_images_row.clear()
    with chat_images_row:
        for idx, img in enumerate(images):
            with ui.card().tight():
                ui.image(f"data:{img['mime']};base64,{base64.b64encode(img['bytes']).decode('ascii')}") \
                    .classes('w-20 h-20')
                ui.button(icon='close', on_click=functools.partial(_on_chat_image_remove, node_id, idx)) \
                    .props('round dense flat size=sm color=negative')
    remaining = CHAT_MAX_IMAGES - len(images)
    chat_images_label.set_text(f'{len(images)}/{CHAT_MAX_IMAGES} images attached ({remaining} more allowed)')


def _open_server_image_picker(on_picked, *, title: str = 'Add image from host filesystem') -> None:
    """Open a dialog for choosing an image file from the host filesystem.

    Lists folders and image files (`BENCHMARK_IMAGE_EXTENSIONS`) of the current directory in a dropdown, starting at the default test-image folder when it exists.

    Args:
        on_picked (Callable): Called with `{'bytes', 'mime', 'name'}` when the user confirms a file.
        title (str, optional): Dialog title.
    """
    start_dir = BENCHMARK_SOURCE_DEFAULT_DIR if os.path.isdir(BENCHMARK_SOURCE_DEFAULT_DIR) else os.path.dirname(__file__)
    state = {'dir': start_dir, 'selected': None}
    with ui.dialog() as dialog, ui.card().classes('w-[32rem]'):
        ui.label(title).classes('text-subtitle1 font-semibold')
        path_label = ui.label(state['dir']).classes('text-caption text-grey q-mb-sm')
        file_select = ui.select({}, label='File / folder').props('dense outlined').classes('w-full')

        def _refresh() -> None:
            """Repopulate the file dropdown for the current directory and clear the selection."""
            options = {}
            parent = os.path.dirname(state['dir'].rstrip('/'))
            if parent and parent != state['dir'].rstrip('/'):
                options['..'] = '.. (up)'
            for entry_name, is_dir in _benchmark_list_dir(state['dir']):
                if not is_dir and os.path.splitext(entry_name)[1].lower() not in BENCHMARK_IMAGE_EXTENSIONS:
                    continue
                options[entry_name] = f'{entry_name}/' if is_dir else entry_name
            file_select.set_options(options, value=None)
            path_label.set_text(state['dir'])
            state['selected'] = None
            add_btn.set_enabled(False)

        def _on_select(e) -> None:
            """Handle a dropdown choice: go up, enter a folder, or remember the chosen file and enable Add."""
            name = e.value
            if not name:
                return
            if name == '..':
                state['dir'] = os.path.dirname(state['dir'].rstrip('/')) or '/'
                _refresh()
                return
            full = os.path.join(state['dir'], name)
            if os.path.isdir(full):
                state['dir'] = full
                _refresh()
                return
            state['selected'] = full
            add_btn.set_enabled(True)

        file_select.on_value_change(_on_select)

        def _on_add() -> None:
            """Read the selected file, pass it to `on_picked` and close the dialog."""
            full = state['selected']
            if not full:
                return
            try:
                data = Path(full).read_bytes()
            except OSError as exc:
                ui.notify(f'failed to read {full}: {exc}', type='negative')
                return
            mime = mimetypes.guess_type(full)[0] or 'image/jpeg'
            on_picked({'bytes': data, 'mime': mime, 'name': os.path.basename(full)})
            dialog.close()

        with ui.row().classes('w-full justify-end q-mt-md'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            add_btn = ui.button('Add', on_click=_on_add)
            add_btn.set_enabled(False)
    _refresh()
    dialog.open()


def _on_chat_add_image_clicked() -> None:
    """Open the image picker to attach an image to the active session, up to `CHAT_MAX_IMAGES`."""
    node_id = chat_endpoint_select.value
    if not node_id:
        ui.notify('select a (V/L)LM server first', type='warning')
        return
    session = _get_chat_session(node_id)
    if len(session['pending_images']) >= CHAT_MAX_IMAGES:
        ui.notify(f'maximum {CHAT_MAX_IMAGES} images -- remove one before adding another', type='warning')
        return

    def _on_picked(img: dict) -> None:
        """Attach the picked image to the session and redraw the thumbnails."""
        session['pending_images'].append(img)
        _chat_render_images(node_id)
        session['last_edit_ts'] = time.time()

    _open_server_image_picker(_on_picked)
    session['last_edit_ts'] = time.time()


def _on_prompt_library_open_clicked() -> None:
    """Open the prompt library dialog: list, tick, delete and add saved prompts (text plus images)."""
    new_images_state: dict = {'images': []}
    pending_checked: dict = {}

    with ui.dialog() as dialog, ui.card().classes('w-[40rem]'):
        ui.label('Prompt library').classes('text-subtitle1 font-semibold')
        library_col = ui.column().classes('w-full gap-1').style('max-height: 260px; overflow-y: auto')

        def _render_library() -> None:
            """Redraw the saved-prompt list from disk and reset the pending checkbox states."""
            entries = _prompt_library_load()
            pending_checked.clear()
            library_col.clear()
            with library_col:
                if not entries:
                    ui.label('No saved prompts yet -- add one below.').classes('text-caption text-grey')
                for entry in entries:
                    pending_checked[entry['id']] = bool(entry.get('checked', False))
                    with ui.row().classes('w-full items-center gap-2'):
                        ui.checkbox(value=bool(entry.get('checked', False))) \
                            .on_value_change(functools.partial(_on_checked_change, entry['id']))
                        num_images = len(entry.get('image_paths') or [])
                        suffix = f" ({num_images} image{'s' if num_images != 1 else ''})" if num_images else ''
                        ui.label(f"{entry['title']}{suffix}").classes('flex-grow')
                        ui.button(icon='delete', on_click=functools.partial(_on_delete, entry['id'])) \
                            .props(f'dense flat round size=sm color=negative aria-label="Delete prompt: {entry["title"]}"')

        def _on_checked_change(entry_id: str, e) -> None:
            """Record the new checkbox state of a prompt until Save is clicked."""
            pending_checked[entry_id] = bool(e.value)

        def _on_save_checked_states(_e=None) -> None:
            """Persist the pending checkbox states to the prompt library file."""
            entries = _prompt_library_load()
            for entry in entries:
                if entry['id'] in pending_checked:
                    entry['checked'] = pending_checked[entry['id']]
            _prompt_library_save(entries)
            ui.notify('Prompt checkbox states saved', type='positive')

        def _on_delete(entry_id: str, _e=None) -> None:
            """Delete a saved prompt and redraw the list."""
            _prompt_library_delete(entry_id)
            _render_library()

        ui.separator().classes('q-my-sm')
        ui.label('Add a new prompt').classes('text-caption text-grey-8')
        new_text_input = ui.textarea(label='Prompt text', placeholder='Type a prompt...') \
            .props('dense outlined autogrow').classes('w-full')
        new_images_row = ui.row().classes('w-full gap-2 flex-wrap')

        def _render_new_images() -> None:
            """Redraw the thumbnails and count for the images of the prompt being composed."""
            new_images_row.clear()
            with new_images_row:
                for idx, img in enumerate(new_images_state['images']):
                    with ui.card().tight():
                        ui.image(f"data:{img['mime']};base64,{base64.b64encode(img['bytes']).decode('ascii')}") \
                            .classes('w-16 h-16')
                        ui.button(icon='close', on_click=functools.partial(_on_new_image_remove, idx)) \
                            .props('round dense flat size=sm color=negative')
            new_images_label.set_text(f"{len(new_images_state['images'])} image(s) attached")

        def _on_new_image_remove(idx: int, _e=None) -> None:
            """Remove an image from the prompt being composed."""
            if 0 <= idx < len(new_images_state['images']):
                new_images_state['images'].pop(idx)
            _render_new_images()

        def _on_new_image_add(_e=None) -> None:
            """Open the image picker for the prompt being composed, up to `CHAT_MAX_IMAGES`."""
            if len(new_images_state['images']) >= CHAT_MAX_IMAGES:
                ui.notify(f'maximum {CHAT_MAX_IMAGES} images -- remove one before adding another', type='warning')
                return

            def _on_picked(img: dict) -> None:
                """Add the picked image to the prompt being composed."""
                new_images_state['images'].append(img)
                _render_new_images()

            _open_server_image_picker(_on_picked, title='Add image to this prompt')

        with ui.row().classes('w-full items-center gap-2'):
            ui.button('Add image(s)', icon='add_photo_alternate', on_click=_on_new_image_add).props('dense outline')
            new_images_label = ui.label('0 image(s) attached').classes('text-caption text-grey')

        def _on_add_prompt(_e=None) -> None:
            """Save the composed prompt to the library, then clear the form and redraw."""
            text = (new_text_input.value or '').strip()
            images = new_images_state['images']
            if not text and not images:
                ui.notify('type a prompt or attach an image first', type='warning')
                return
            _prompt_library_add(text, images)
            new_text_input.set_value('')
            new_images_state['images'] = []
            _render_new_images()
            _render_library()

        with ui.row().classes('w-full justify-end gap-2 q-mt-md'):
            ui.button('Close', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=_on_save_checked_states).props('outline')
            ui.button('Add Prompt', on_click=_on_add_prompt)

    _render_library()
    _render_new_images()
    dialog.open()


# Quasar props of the replay button in its idle (play) and running (stop) states.
_PLAY_BTN_BASE_PROPS = 'dense outline round size=sm aria-label="Loop selected prompts"'
_PLAY_BTN_IDLE_PROPS = f'{_PLAY_BTN_BASE_PROPS} icon=play_arrow'
_PLAY_BTN_RUNNING_PROPS_ADD = 'icon=stop color=negative'


async def _prompt_library_play_loop(node_id: str) -> None:
    """Replay the ticked library prompts against the selected server until stopped.

    Cycles through the checked prompts, sending each as a user message and streaming the reply, with prompts spread round-robin over the running instances. Stops when `session['playing']` becomes False, or when no instance or no checked prompt exists. Always resets the playing state on exit.

    Args:
        node_id (str): Session whose instances and playing flag are used.
    """

    session = _get_chat_session(node_id)
    try:
        while session['playing']:
            instances = [i for i in (_chat_groups.get(node_id) or []) if i.get('running')]
            if not instances:
                if node_id == _chat_active_node_id:
                    ui.notify('no running (V/L)LM server selected -- click refresh first', type='warning')
                break
            entries = [e for e in _prompt_library_load() if e.get('checked')]
            if not entries:
                if node_id == _chat_active_node_id:
                    ui.notify('no prompts selected -- tick checkboxes and Save in the Prompt Library first', type='warning')
                break
            for i, entry in enumerate(entries):
                if not session['playing']:
                    break
                images = []
                for path in entry.get('image_paths') or []:
                    try:
                        with open(path, 'rb') as f:
                            data = f.read()
                    except OSError:
                        continue
                    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
                    images.append({'bytes': data, 'mime': mime, 'name': os.path.basename(path)})
                prompt = entry.get('text') or ''
                _chat_session_record_message(node_id, 'user', prompt, num_images=len(images))
                max_new_tokens = max(1, int(chat_max_tokens_input.value or 128))
                inst = instances[i % len(instances)]
                await _chat_stream_one(
                    node_id, _chat_instance_base_url(inst['port']), images, prompt, max_new_tokens,
                    f"{inst['name']}, prompt {i + 1}/{len(entries)}",
                )
    finally:
        session['playing'] = False
        session['play_task'] = None
        if node_id == _chat_active_node_id:
            _chat_sync_controls_for_active()


def _on_prompt_library_play_clicked() -> None:
    """Start prompt replay for the selected server, or request a stop (after the current prompt) if it is already playing."""
    node_id = chat_endpoint_select.value
    if not node_id:
        ui.notify('select a (V/L)LM server first', type='warning')
        return
    session = _get_chat_session(node_id)
    if session['playing']:
        session['playing'] = False
        ui.notify('Stopping prompt replay after the current prompt...', type='info')
        return
    session['playing'] = True
    session['play_task'] = asyncio.create_task(_prompt_library_play_loop(node_id))
    _chat_sync_controls_for_active()


def _chat_sync_controls_for_active() -> None:
    """Update the play button look (play/stop) and the Send button enabled state to match the active session."""
    session = _chat_sessions.get(_chat_active_node_id) if _chat_active_node_id else None
    playing = bool(session and session['playing'])
    play_btn.props(remove='color')
    play_btn.props(add=_PLAY_BTN_RUNNING_PROPS_ADD if playing else _PLAY_BTN_IDLE_PROPS)
    if playing:
        play_btn.classes(remove='muted-outline-btn')
    else:
        play_btn.classes(add='muted-outline-btn')
    if playing:
        send_btn.disable()
    else:
        send_btn.enable()


def _on_chat_image_remove(node_id: str, idx: int, _e=None) -> None:
    """Remove an attached image from a session and redraw the thumbnails."""
    session = _get_chat_session(node_id)
    if 0 <= idx < len(session['pending_images']):
        session['pending_images'].pop(idx)
    _chat_render_images(node_id)
    session['last_edit_ts'] = time.time()


def _on_chat_text_changed(_e) -> None:
    """Record the edit time and save the draft text of the selected session."""
    node_id = chat_endpoint_select.value
    if not node_id:
        return
    session = _get_chat_session(node_id)
    session['last_edit_ts'] = time.time()
    session['draft_text'] = chat_text_input.value or ''


async def _chat_token_budget_tick() -> None:
    """Update the token-estimate label for the current draft (called from a timer).

    Skips while a count is running, while the user is still typing (`CHAT_TOKEN_DEBOUNCE_S`) and when the text and image count are unchanged. Text tokens come from the server's tokenizer, with a words x 1.3 estimate if that fails. Each image counts as `ceil(w/28) * ceil(h/28)` tokens using the node's resize size (default 512x512). Compared against the instance's context length when known.
    """
    node_id = chat_endpoint_select.value
    if not node_id:
        return
    session = _get_chat_session(node_id)
    if session['busy']:
        return
    if time.time() - session['last_edit_ts'] < CHAT_TOKEN_DEBOUNCE_S:
        return
    text = chat_text_input.value or ''
    num_images = len(session['pending_images'])
    cache_key = (text, num_images, node_id)
    if cache_key == session['last_counted_key']:
        return
    instances = _chat_groups.get(node_id) or []
    if not instances:
        chat_budget_label.set_text('select a running (V/L)LM server above to estimate tokens' if (text or num_images) else '')
        session['last_counted_key'] = cache_key
        return
    session['busy'] = True
    try:
        inst = instances[0]
        text_tokens = 0
        if text.strip():
            try:
                async with AsyncAxLlmClient(_chat_instance_base_url(inst['port']), timeout=10.0) as client:
                    text_tokens = await client.count_tokens(text)
            except Exception:
                text_tokens = int(max(1, len(text.split())) * 1.3)
        node_data = (_node_by_id(node_id) or {}).get('data', {})
        resize_w = int(node_data.get('resize_width') or 512)
        resize_h = int(node_data.get('resize_height') or 512)
        tokens_per_image = math.ceil(resize_w / CHAT_VISION_TOKEN_PATCH_PX) * math.ceil(resize_h / CHAT_VISION_TOKEN_PATCH_PX)
        image_tokens = num_images * tokens_per_image
        total = text_tokens + image_tokens
        context_length = inst.get('context_length')
        if context_length:
            remaining = context_length - total
            detail = f' ({text_tokens} text + {image_tokens} est. image)' if num_images else ''
            chat_budget_label.set_text(f'~{total} tokens{detail} / {context_length} context -- {remaining} remaining')
            chat_budget_label.classes(
                replace='text-caption ' + ('text-negative' if remaining < 0 else 'text-grey'))
        else:
            chat_budget_label.set_text(f'~{total} tokens (context length unknown for this server)')
            chat_budget_label.classes(replace='text-caption text-grey')
        session['last_counted_key'] = cache_key
    finally:
        session['busy'] = False


def _chat_render_message_bubble(role: str, text: str, *, num_images: int = 0) -> None:
    """Append a finished message bubble (user, assistant or error) to the chat log and scroll to the bottom."""
    style = {'user': 'bg-blue-1', 'assistant': 'bg-grey-2', 'error': 'bg-red-1'}.get(role, 'bg-grey-2')
    label = {'user': 'You', 'assistant': 'Server', 'error': 'Error'}.get(role, role)
    suffix = f" (+{num_images} image{'s' if num_images != 1 else ''})" if num_images else ''
    with chat_log:
        with ui.card().classes(f'w-full {style}').tight():
            with ui.card_section():
                ui.label(f'{label}{suffix}').classes('text-caption text-grey-8')
                ui.label(text or '(empty)').style('white-space: pre-wrap')
    chat_log.scroll_to(percent=1.0)


def _chat_render_placeholder_bubble(role: str, text: str):
    """Append a bubble whose text is updated while streaming and return its text label."""
    style = {'user': 'bg-blue-1', 'assistant': 'bg-grey-2', 'error': 'bg-red-1'}.get(role, 'bg-grey-2')
    label = {'user': 'You', 'assistant': 'Server', 'error': 'Error'}.get(role, role)
    with chat_log:
        with ui.card().classes(f'w-full {style}').tight():
            with ui.card_section():
                ui.label(label).classes('text-caption text-grey-8')
                body = ui.label(text).style('white-space: pre-wrap')
    chat_log.scroll_to(percent=1.0)
    return body


def _chat_session_record_message(node_id: str, role: str, text: str, *, num_images: int = 0) -> int:
    """Store a finished message in the session and render it if the session is active.

    Returns:
        int: Index of the message in the session.
    """
    session = _get_chat_session(node_id)
    idx = len(session['messages'])
    session['messages'].append({'role': role, 'text': text, 'num_images': num_images, 'final': True})
    if node_id == _chat_active_node_id:
        _chat_render_message_bubble(role, text, num_images=num_images)
    return idx


def _chat_session_start_placeholder(node_id: str, role: str, text: str) -> int:
    """Store an unfinished message in the session and render a live bubble if the session is active.

    Returns:
        int: Index of the message, used by `_chat_session_update_placeholder`.
    """
    session = _get_chat_session(node_id)
    idx = len(session['messages'])
    session['messages'].append({'role': role, 'text': text, 'num_images': 0, 'final': False})
    if node_id == _chat_active_node_id:
        _active_message_labels[idx] = _chat_render_placeholder_bubble(role, text)
    return idx


def _chat_session_update_placeholder(node_id: str, idx: int, text: str, *, final: bool = False) -> None:
    """Replace the text of an in-progress message, mark it final if requested, and update the bubble if it is on screen."""
    session = _get_chat_session(node_id)
    session['messages'][idx]['text'] = text
    if final:
        session['messages'][idx]['final'] = True
    if node_id == _chat_active_node_id:
        body = _active_message_labels.get(idx)
        if body is not None:
            body.set_text(text)
            chat_log.scroll_to(percent=1.0)


def _chat_activate_session(new_node_id: str | None) -> None:
    """Switch the chat view to another server group.

    Saves the draft of the old session, rebuilds the log, draft text, thumbnails and metrics from the new session, and clears the token label.

    Args:
        new_node_id (str | None): Session to show, or None to show an empty view.
    """
    global _chat_active_node_id
    if new_node_id == _chat_active_node_id:
        _chat_sync_controls_for_active()
        return

    old_node_id = _chat_active_node_id
    if old_node_id is not None and old_node_id in _chat_sessions:
        _chat_sessions[old_node_id]['draft_text'] = chat_text_input.value or ''

    _active_message_labels.clear()
    chat_log.clear()
    _chat_active_node_id = new_node_id
    if new_node_id:
        session = _get_chat_session(new_node_id)
        for idx, msg in enumerate(session['messages']):
            if msg['role'] == 'assistant' and not msg['final']:
                _active_message_labels[idx] = _chat_render_placeholder_bubble(msg['role'], msg['text'])
            else:
                _chat_render_message_bubble(msg['role'], msg['text'], num_images=msg['num_images'])
        chat_text_input.set_value(session['draft_text'])
    else:
        chat_text_input.set_value('')
    _chat_render_images(new_node_id)
    _chat_update_metrics_label(new_node_id)
    chat_budget_label.set_text('')
    _chat_sync_controls_for_active()


def _chat_record_metrics(node_id: str, ttft: float, tok_per_sec: float | None) -> None:
    """Append a (TTFT, tokens/s) sample to the session and refresh the metrics label if it is active."""
    session = _get_chat_session(node_id)
    session['metrics'].append((ttft, tok_per_sec))
    if node_id == _chat_active_node_id:
        _chat_update_metrics_label(node_id)


def _chat_update_metrics_label(node_id: str | None) -> None:
    """Show the average TTFT and tokens/s over the stored samples of a session, or clear the label when there are none."""
    buf = _chat_sessions.get(node_id, {}).get('metrics') if node_id else None
    if not buf:
        chat_metrics_label.set_text('')
        return
    avg_ttft = sum(t for t, _ in buf) / len(buf)
    tps_samples = [s for _, s in buf if s is not None]
    tps_text = f'{sum(tps_samples) / len(tps_samples):.1f} tok/s' if tps_samples else 'n/a tok/s'
    chat_metrics_label.set_text(f'avg (last {len(buf)}): TTFT {avg_ttft:.2f}s · {tps_text}')


# Errors treated as transient by _is_retryable_stream_error; backoffs are seconds before each retry.
_STREAM_RETRYABLE_EXCEPTIONS = (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.PoolTimeout)
_STREAM_RETRYABLE_ENGINE_ERROR_PREFIX = 'infer_stream() failed mid-stream:'
_STREAM_RETRY_BACKOFFS_S = (1.0, 3.0)


def _is_retryable_stream_error(exc: Exception) -> bool:
    """Return True for connection-level errors and engine mid-stream failures that are worth retrying."""
    if isinstance(exc, _STREAM_RETRYABLE_EXCEPTIONS):
        return True
    return isinstance(exc, RuntimeError) and str(exc).startswith(_STREAM_RETRYABLE_ENGINE_ERROR_PREFIX)


async def _chat_stream_one(
        node_id: str, base_url: str, images: list[dict], prompt: str, max_new_tokens: int, tag: str) -> None:
    """Send one request to a (V/L)LM instance and stream the reply into a chat bubble.

    Uses the VLM client when images are attached, else the LLM client. On completion the bubble shows time to first token and tokens/s (token count from the server, omitted if unavailable) and the sample is recorded. Retryable connection errors are retried after the delays in `_STREAM_RETRY_BACKOFFS_S`; other errors are written into the bubble. Does not raise.

    Args:
        node_id (str): Session to write to.
        base_url (str): Base URL of the instance.
        images (list[dict]): Images as dicts with `bytes` and `mime`; may be empty.
        prompt (str): Prompt text.
        max_new_tokens (int): Generation limit.
        tag (str): Label shown at the start of the bubble.
    """

    idx = _chat_session_start_placeholder(node_id, 'assistant', f'[{tag}] ...')
    attempt = 0
    while True:
        text = ''
        try:
            if images:
                client_cm = AsyncAxVlmClient(base_url, timeout=120.0)
            else:
                client_cm = AsyncAxLlmClient(base_url, timeout=120.0)
            async with client_cm as client:
                stream = (
                    client.infer_stream(
                        [img['bytes'] for img in images], prompt or None,
                        image_mime_type=images[0]['mime'], max_new_tokens=max_new_tokens,
                    )
                    if images
                    else client.infer_stream(prompt, max_new_tokens=max_new_tokens)
                )
                t_start = time.monotonic()
                t_first = None
                async for delta in stream:
                    if t_first is None:
                        t_first = time.monotonic()
                    text += delta
                    _chat_session_update_placeholder(node_id, idx, f'[{tag}] {text}')
                t_end = time.monotonic()
                if not text:
                    _chat_session_update_placeholder(node_id, idx, f'[{tag}] (empty response)', final=True)
                    return
                ttft = t_first - t_start
                decode_s = t_end - t_first
                tok_per_sec = None
                if decode_s > 0:
                    try:
                        completion_tokens = await client.count_tokens(text)
                        tok_per_sec = completion_tokens / decode_s
                    except Exception:
                        tok_per_sec = None
                suffix = f' · TTFT {ttft:.2f}s' + (f' · {tok_per_sec:.1f} tok/s' if tok_per_sec is not None else '')
                _chat_session_update_placeholder(node_id, idx, f'[{tag}{suffix}] {text}', final=True)
                _chat_record_metrics(node_id, ttft, tok_per_sec)
            return
        except Exception as exc:
            if not _is_retryable_stream_error(exc) or attempt >= len(_STREAM_RETRY_BACKOFFS_S):
                _chat_session_update_placeholder(node_id, idx, f'[{tag}] error: {exc}', final=True)
                return
            backoff = _STREAM_RETRY_BACKOFFS_S[attempt]
            attempt += 1
            total_attempts = len(_STREAM_RETRY_BACKOFFS_S) + 1
            _chat_session_update_placeholder(
                node_id, idx,
                f'[{tag}] connection dropped ({exc.__class__.__name__}) -- '
                f'retrying in {backoff:.0f}s (attempt {attempt + 1}/{total_attempts})...')
            await asyncio.sleep(backoff)


async def _on_chat_send_clicked() -> None:
    """Send the current message to the selected server group.

    Fires `concurrency` simultaneous requests spread round-robin over the running instances, waits for all of them, then clears the input and attached images.
    """
    node_id = chat_endpoint_select.value
    if not node_id:
        ui.notify('no running (V/L)LM server selected -- click refresh first', type='warning')
        return
    session = _get_chat_session(node_id)
    instances = [i for i in (_chat_groups.get(node_id) or []) if i.get('running')]
    if not instances:
        ui.notify('no running (V/L)LM server selected -- click refresh first', type='warning')
        return
    prompt = (chat_text_input.value or '').strip()
    images = list(session['pending_images'])
    if not prompt and not images:
        ui.notify('type a message or attach an image first', type='warning')
        return
    concurrency = max(1, int(chat_concurrency_input.value or 1))
    max_new_tokens = max(1, int(chat_max_tokens_input.value or 128))
    if node_id == _chat_active_node_id:
        send_btn.disable()
    _chat_session_record_message(node_id, 'user', prompt, num_images=len(images))
    try:
        tasks = [
            _chat_stream_one(
                node_id, _chat_instance_base_url(instances[i % len(instances)]['port']), images, prompt, max_new_tokens,
                f"{instances[i % len(instances)]['name']}" + (f', #{i + 1}/{concurrency}' if concurrency > 1 else ''),
            )
            for i in range(concurrency)
        ]
        await asyncio.gather(*tasks)
    finally:
        if node_id == _chat_active_node_id:
            send_btn.enable()
    if node_id == _chat_active_node_id:
        chat_text_input.set_value('')
    session['pending_images'] = []
    _chat_render_images(node_id)
    session['last_edit_ts'] = time.time()


def _on_chat_clear_clicked() -> None:
    """Clear the messages, images, metrics and draft of the selected session and the view."""
    node_id = chat_endpoint_select.value
    if not node_id:
        return
    session = _get_chat_session(node_id)
    session['messages'] = []
    session['pending_images'] = []
    session['metrics'].clear()
    session['draft_text'] = ''
    session['last_counted_key'] = None
    _active_message_labels.clear()
    chat_log.clear()
    chat_text_input.set_value('')
    _chat_render_images(node_id)
    chat_budget_label.set_text('')
    chat_metrics_label.set_text('')
