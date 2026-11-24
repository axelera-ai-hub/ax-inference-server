#!/usr/bin/env python3

"""Replay a mouse and keyboard recording of a Pipeline Editor session in a visible Chromium window via Playwright.

Usage: replay_recording.py <recording.json> [base_url]. The recording is the JSON event list written by the app's debug-mode capture.
"""

import json
import sys

from playwright.sync_api import sync_playwright

# Maps DOM MouseEvent.button codes to Playwright button names.
_BUTTON_NAMES = {0: 'left', 1: 'middle', 2: 'right'}

# Upper bound on the pause inserted between two recorded events, so long idle gaps do not stall the replay.
_MAX_WAIT_MS = 2000


def main() -> int:
    """Replay a recorded event list against a running app and save a final screenshot.

    Reads sys.argv: argv[1] is the recording path, argv[2] is the optional base URL (default http://127.0.0.1:8080). The recording is a JSON list of events, optionally starting with a `meta` event that carries the viewport `width` and `height` (default 1280x800). Events carry a millisecond timestamp `t`; supported types are mousemove, mousedown, mouseup, wheel, keydown and keyup, and unknown types are skipped with a message. Chromium runs headed, waits for a `.vue-flow__node` to appear, writes `tests/_replay_final.png` (relative to the current directory), then waits for Enter before closing.

    Returns:
        int: 0 on success, 2 if no recording path was given, 1 if the recording is empty.
    """
    if len(sys.argv) < 2:
        print('usage: replay_recording.py <path_to_recording.json> [base_url]')
        return 2
    recording_path = sys.argv[1]
    base_url = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:8080'

    with open(recording_path) as f:
        events = json.load(f)
    if not events:
        print('recording is empty -- nothing to replay')
        return 1

    meta = events[0] if events[0].get('type') == 'meta' else None
    steps = events[1:] if meta else events
    viewport = {'width': meta['width'], 'height': meta['height']} if meta else {'width': 1280, 'height': 800}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport=viewport)
        page.on('pageerror', lambda exc: print('PAGE ERROR:', exc))
        page.on('console', lambda msg: print(f'CONSOLE[{msg.type}]:', msg.text))

        page.goto(base_url, wait_until='networkidle')
        page.wait_for_selector('.vue-flow__node', state='visible', timeout=10000)

        print(f'replaying {len(steps)} events (viewport={viewport})...')
        last_t = 0
        for i, event in enumerate(steps):
            wait_ms = min(event.get('t', last_t) - last_t, _MAX_WAIT_MS)
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)
            last_t = event.get('t', last_t)

            etype = event.get('type')
            if etype == 'mousemove':
                page.mouse.move(event['x'], event['y'])
            elif etype == 'mousedown':
                page.mouse.move(event['x'], event['y'])
                page.mouse.down(button=_BUTTON_NAMES.get(event.get('button', 0), 'left'))
            elif etype == 'mouseup':
                page.mouse.move(event['x'], event['y'])
                page.mouse.up(button=_BUTTON_NAMES.get(event.get('button', 0), 'left'))
            elif etype == 'wheel':
                page.mouse.move(event['x'], event['y'])
                page.mouse.wheel(event.get('deltaX', 0), event.get('deltaY', 0))
            elif etype == 'keydown':
                page.keyboard.down(event['key'])
            elif etype == 'keyup':
                page.keyboard.up(event['key'])
            else:
                print(f'  [{i}] skipping unknown event type: {etype!r}')

        page.wait_for_timeout(500)
        page.screenshot(path='tests/_replay_final.png')
        print('replay complete -- screenshot saved to tests/_replay_final.png')
        input('Press Enter to close the browser...')
        browser.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
