"""Agent control surface of the GUI: the /_agent/* HTTP routes and the browser-side helpers behind them.

Lets an automated client (see agent_mcp_server.py and the end-to-end tests) read and drive a browser tab: click, hover, set fields, operate dropdowns, edit the canvas graph, read text, tooltips and toasts, take screenshots, fetch benchmark frames and draw highlights. Each helper runs JavaScript in the target tab through NiceGUI's run_javascript or calls PipelineFlow methods directly.

Note:
    Helpers return plain dicts: {'ok': True, ...} on success or {'ok': False, 'error': <code>, ...} on failure (js_exception and js_error mean the browser call raised or returned a non-dict). Routes require the X-Agent-Key header only when GUI_AGENT_API_KEY is set. While a modal dialog is open, lookups are scoped to it, and a dialog counts as open only while Quasar's 'q-dialog--modal' class is present, which is dropped as soon as a close starts.
"""

import asyncio
import base64
import json
import os
import time
from collections import deque
from typing import Optional

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

from nicegui import Client, app, core, ui

from components.pipeline_flow import PipelineFlow
from node_catalog import NODE_CATALOG, PALETTE_TREE

# Shared with app.py and benchmark.py through core.app.state.
BENCHMARK_SOURCES: dict = core.app.state.benchmark_sources
current_graph: dict = core.app.state.current_graph

# Set by configure().
_read_file_bytes = None
_benchmark_ring_buffer_names = None


def configure(*, read_file_bytes, benchmark_ring_buffer_names) -> None:
    """Provide the benchmark helpers owned by benchmark.py.

    Args:
        read_file_bytes: Callable returning the bytes of a file path.
        benchmark_ring_buffer_names: Callable returning the sorted frame file names of a frame directory.
    """
    global _read_file_bytes, _benchmark_ring_buffer_names
    _read_file_bytes = read_file_bytes
    _benchmark_ring_buffer_names = benchmark_ring_buffer_names


if not hasattr(core.app.state, 'agent_notification_buffers'):
    core.app.state.agent_notification_buffers = {}
if not hasattr(core.app.state, 'agent_notification_seq'):
    core.app.state.agent_notification_seq = 0
AGENT_NOTIFICATION_BUFFERS: dict = core.app.state.agent_notification_buffers
# Toasts kept per client.
AGENT_NOTIFICATION_BUFFER_SIZE = 200

# Keep the real ui.notify even if this module is imported again after wrapping.
_agent_original_notify = getattr(ui.notify, '_agent_unwrapped', None) or ui.notify


def _agent_notify_wrapper(message, **kwargs):
    """Record a toast in the calling client's notification buffer, then call the original ui.notify.

    The client id comes from the current UI context; outside a client context nothing is recorded. Each record has an increasing 'id', a timestamp, the message, its type and position.

    Args:
        message: Notification text.
        **kwargs: Passed through to ui.notify; 'type' and 'position' are also recorded.

    Returns:
        The return value of the original ui.notify.
    """
    try:
        client_id = ui.context.client.id
    except Exception:
        client_id = None
    if client_id is not None:
        buf = AGENT_NOTIFICATION_BUFFERS.setdefault(
            client_id, deque(maxlen=AGENT_NOTIFICATION_BUFFER_SIZE))
        core.app.state.agent_notification_seq += 1
        buf.append({
            'id': core.app.state.agent_notification_seq,
            'ts': time.time(),
            'message': str(message),
            'type': kwargs.get('type'),
            'position': kwargs.get('position', 'bottom'),
        })
    return _agent_original_notify(message, **kwargs)


# Install the recording wrapper once.
if not getattr(ui.notify, '_agent_unwrapped', None):
    _agent_notify_wrapper._agent_unwrapped = _agent_original_notify
    ui.notify = _agent_notify_wrapper


async def _agent_click(client: Client, text: str) -> dict:
    """Click the element whose visible text, icon name, aria-label or alt matches.

    Considers buttons, tabs, checkboxes/toggles, radios, labeled images and palette tree rows. An exact (case-insensitive) match beats a substring match; several equally good matches are reported as ambiguous. With a modal dialog open, the dialog is searched first and then the page outside any dialog. Clicking a palette category row clicks its expand arrow.

    Args:
        client (Client): Target browser tab.
        text (str): Text to match.

    Returns:
        dict: {'ok': True, 'kind': ..., 'text': ...} or {'ok': False, 'error': 'not_found' | 'ambiguous', 'matched_count': ..., 'candidates': [...]}.
    """
    js = f"""
        (() => {{
            const target = {text!r}.trim().toLowerCase();
            // offsetParent is unreliable here: Chromium reports it as null for
            // any position:fixed element regardless of whether it's actually
            // shown, and Quasar's dialogs/menus are position:fixed.
            // offsetWidth/offsetHeight/getClientRects() all correctly read 0
            // for a genuinely display:none-hidden element without that false
            // negative.
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const isDisabled = el => !!(el.disabled || el.getAttribute('aria-disabled') === 'true'
                                         || el.classList.contains('disabled') || el.classList.contains('q-btn--disable'));
            const labelsFor = el => {{
                const icon = el.querySelector('i.material-icons, i.q-icon');
                // el.textContent alone concatenates an icon's ligature text
                // with the real label (e.g. a QTree leaf like "Isovision
                // Demo" next to a folder icon reads as "scienceIsovision
                // Demo"), which breaks exact-match scoring against the
                // label a human would actually type. Strip the icon's own
                // text out of "own" -- it's already captured separately
                // below for matching by icon name.
                let own = el.textContent.trim();
                if (icon && icon.textContent.trim()) {{
                    const withoutIcon = el.cloneNode(true);
                    const iconClone = withoutIcon.querySelector('i.material-icons, i.q-icon');
                    if (iconClone) iconClone.remove();
                    own = withoutIcon.textContent.trim();
                }}
                let rowText = '';
                if (!own && (el.classList.contains('q-checkbox') || el.classList.contains('q-toggle'))) {{
                    // el itself carries Quasar's own ".row" flex-utility class
                    // (q-checkbox/q-toggle's root element does), so a plain
                    // closest('.row') self-matches and returns '' instead of
                    // climbing to the actual row wrapper that holds the
                    // sibling label -- start from the parent instead.
                    const row = el.parentElement ? el.parentElement.closest('.row') : null;
                    if (row) rowText = row.textContent.trim();
                }}
                return [
                    own,
                    rowText,
                    icon ? icon.textContent.trim() : '',
                    (el.getAttribute('aria-label') || '').trim(),
                    (el.getAttribute('alt') || '').trim(),
                ].filter(Boolean);
            }};
            const collect = (root) => {{
                const seen = new Set();
                const out = [];
                const add = (el, kind) => {{ if (!seen.has(el)) {{ seen.add(el); out.push({{el, kind}}); }} }};
                root.querySelectorAll('button, .q-btn').forEach(el => {{ if (isVisible(el) && !isDisabled(el)) add(el, 'button'); }});
                root.querySelectorAll('.q-tab').forEach(el => {{ if (isVisible(el)) add(el, 'tab'); }});
                root.querySelectorAll('.q-checkbox, .q-toggle').forEach(el => {{ if (isVisible(el) && !isDisabled(el)) add(el, 'toggle'); }});
                // ui.radio() (e.g. the Three-Stage Conditional Cascade
                // wizard's "Primary model"/"Secondary model"/"Conditional
                // tertiary model" stage switcher) renders each option as a
                // .q-radio, which none of the selectors above match.
                root.querySelectorAll('.q-radio').forEach(el => {{ if (isVisible(el) && !isDisabled(el)) add(el, 'toggle'); }});
                // ui.image() (QImg) is reachable via click(text=...) only
                // through its .q-img wrapper root, not its inner native
                // <img>: alt goes onto QImg's inner <img> (which Quasar
                // itself marks aria-hidden="true" -- decorative, not meant
                // to be the interactive target), while aria-label (plus
                // role="img") goes onto QImg's own .q-img wrapper root, the
                // real visual element a click should land on. Matching the
                // inner <img> by alt too would double-count one visual
                // thumbnail as two candidates and make click() misreport a
                // perfectly unambiguous target as 'ambiguous' -- only the
                // .q-img root is matched here. A labeled thumbnail (see
                // _build_source_tile) is clickable the same way any other
                // labeled control is.
                root.querySelectorAll('.q-img[aria-label], img[aria-label]').forEach(el => {{ if (isVisible(el)) add(el, 'image'); }});
                // The node-palette (PALETTE_TREE, ui.tree(... on_select=
                // _on_palette_select)) was never reachable via click(text=...)
                // before this -- a category ("Examples") or leaf ("Isovision
                // Demo") row is a .q-tree__node-header, none of the kinds
                // above. A real click() here fires Quasar QTree's own native
                // listener the same way a human's click would: expanding a
                // category and/or firing on_select for a leaf, so no separate
                // "expand" primitive is needed.
                root.querySelectorAll('.q-tree__node-header').forEach(el => {{ if (isVisible(el)) add(el, 'tree-node'); }});
                return out;
            }};
            const score = c => {{
                const labels = labelsFor(c.el).map(l => l.toLowerCase());
                if (labels.some(l => l === target)) return 2;
                if (labels.some(l => l.includes(target))) return 1;
                return 0;
            }};
            const pickBest = (candidates) => {{
                const scored = candidates.map(c => ({{el: c.el, kind: c.kind, score: score(c)}})).filter(c => c.score > 0);
                if (scored.length === 0) return {{ok: false, error: 'not_found'}};
                const best = Math.max(...scored.map(c => c.score));
                const top = scored.filter(c => c.score === best);
                if (top.length > 1) {{
                    return {{ok: false, error: 'ambiguous', matched_count: top.length,
                              candidates: top.map(c => c.el.textContent.trim().slice(0, 40))}};
                }}
                return {{ok: true, el: top[0].el, kind: top[0].kind}};
            }};

            // A dialog mid-close still reads as isVisible (nonzero size, still
            // attached) for a brief window before Quasar unmounts it -- see
            // _agent_get_state's own dialog_open definition for why
            // 'q-dialog--modal' (swapped for '--seamless' the instant a close
            // starts, well before the node's size/attachment change) is the
            // reliable signal, not isVisible alone. Every dialog-scoping site
            // in this module must agree with that definition, or a caller can
            // act on a control it wrongly believes is still covered by a
            // dialog that is, in truth, already closing.
            const dialogs = [...document.querySelectorAll('.q-dialog')]
                .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
            const dialog = dialogs[dialogs.length - 1];
            let result;
            if (dialog) {{
                result = pickBest(collect(dialog));
                if (!result.ok && result.error === 'not_found') {{
                    result = pickBest(collect(document).filter(c => !c.el.closest('.q-dialog')));
                }}
            }} else {{
                result = pickBest(collect(document));
            }}
            if (!result.ok) {{
                return {{ok: false, error: result.error, matched_count: result.matched_count || 0,
                          candidates: result.candidates || []}};
            }}
            // A tree category row (e.g. "Examples") only expands/collapses
            // when Quasar's own .q-tree__arrow icon is clicked -- clicking
            // elsewhere on the .q-tree__node-header row does nothing (see
            // _agent_add_node's own expand_js, which already had to work
            // around this the same way). A leaf row (no arrow) has no such
            // quirk -- clicking the header itself fires its on_select.
            let clickTarget = result.el;
            if (result.kind === 'tree-node') {{
                const arrow = result.el.querySelector('.q-tree__arrow');
                if (arrow) clickTarget = arrow;
            }}
            clickTarget.click();
            return {{ok: true, kind: result.kind, text: result.el.textContent.trim().slice(0, 60)}};
        }})()
    """
    try:
        result = await client.run_javascript(js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    return result if isinstance(result, dict) else {'ok': False, 'error': 'js_error'}


async def _agent_hover(client: Client, text: str, action: str = 'enter') -> dict:
    """Dispatch enter or leave mouse events on the element matching the text.

    Matching is as in _agent_click but over a wider element set (anything with an aria-label too) and without dialog scoping.

    Args:
        client (Client): Target browser tab.
        text (str): Text to match.
        action (str, optional): 'enter' or 'leave'. Defaults to 'enter'.

    Returns:
        dict: {'ok': True, 'text': ...} or {'ok': False, 'error': 'not_found' | 'ambiguous', ...}.
    """

    js = f"""
        (() => {{
            const target = {text!r}.trim().toLowerCase();
            const action = {action!r};
            // offsetParent is unreliable here: Chromium reports it as null for
            // any position:fixed element regardless of whether it's actually
            // shown, and Quasar's dialogs/menus are position:fixed.
            // offsetWidth/offsetHeight/getClientRects() all correctly read 0
            // for a genuinely display:none-hidden element without that false
            // negative.
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const labelsFor = el => {{
                const icon = el.querySelector('i.material-icons, i.q-icon');
                return [
                    el.textContent.trim(),
                    icon ? icon.textContent.trim() : '',
                    (el.getAttribute('aria-label') || '').trim(),
                    (el.getAttribute('alt') || '').trim(),
                ].filter(Boolean);
            }};
            const seen = new Set();
            const candidates = [];
            document.querySelectorAll('button, .q-btn, .q-tab, .q-checkbox, .q-toggle, [aria-label]').forEach(el => {{
                if (seen.has(el) || !isVisible(el)) return;
                seen.add(el);
                candidates.push(el);
            }});
            const score = el => {{
                const labels = labelsFor(el).map(l => l.toLowerCase());
                if (labels.some(l => l === target)) return 2;
                if (labels.some(l => l.includes(target))) return 1;
                return 0;
            }};
            const scored = candidates.map(el => ({{el, score: score(el)}})).filter(c => c.score > 0);
            if (scored.length === 0) return {{ok: false, error: 'not_found'}};
            const best = Math.max(...scored.map(c => c.score));
            const top = scored.filter(c => c.score === best);
            if (top.length > 1) {{
                return {{ok: false, error: 'ambiguous', matched_count: top.length,
                          candidates: top.map(c => c.el.textContent.trim().slice(0, 40))}};
            }}
            const el = top[0].el;
            const rect = el.getBoundingClientRect();
            const opts = {{bubbles: true, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2}};
            if (action === 'leave') {{
                el.dispatchEvent(new MouseEvent('mouseout', opts));
                el.dispatchEvent(new MouseEvent('mouseleave', opts));
                el.dispatchEvent(new MouseEvent('pointerleave', opts));
            }} else {{
                el.dispatchEvent(new MouseEvent('pointerenter', opts));
                el.dispatchEvent(new MouseEvent('mouseenter', opts));
                el.dispatchEvent(new MouseEvent('mouseover', opts));
            }}
            return {{ok: true, text: el.textContent.trim().slice(0, 60)}};
        }})()
    """
    try:
        result = await client.run_javascript(js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    return result if isinstance(result, dict) else {'ok': False, 'error': 'js_error'}


async def _agent_set_field(client: Client, label: str, value: str, scope_id: Optional[str] = None) -> dict:
    """Set a toggle, checkbox, input or select by label.

    A toggle or checkbox is clicked only if its state differs; 'true', '1', 'on' and 'yes' mean on. A writable input gets the value with input, change and blur events. A select is opened and the option is picked by exact text, or by unique substring, scrolling the menu while options remain undiscovered. If the menu was already open it is reused instead of being toggled shut.

    Args:
        client (Client): Target browser tab.
        label (str): Label text of the widget (substring match for fields).
        value (str): New value.
        scope_id (str, optional): data-agent-id of an element to search within instead of the topmost dialog or page.

    Returns:
        dict: {'ok': True, 'kind': 'toggle' | 'input' | 'select', ...} or {'ok': False, 'error': ...} with not_found, ambiguous, disabled, scope_not_found, option_not_found (plus 'rendered_options_seen').
    """

    scope_id_js = json.dumps(scope_id)
    detect_js = f"""
        (() => {{
            const target = {label!r}.trim().toLowerCase();
            const scopeId = {scope_id_js};
            // offsetParent is unreliable here: Chromium reports it as null for
            // any position:fixed element regardless of whether it's actually
            // shown, and Quasar's dialogs/menus are position:fixed.
            // offsetWidth/offsetHeight/getClientRects() all correctly read 0
            // for a genuinely display:none-hidden element without that false
            // negative.
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const norm = s => (s || '').trim().toLowerCase();
            // A dialog mid-close still reads as isVisible (nonzero size, still
            // attached) for a brief window before Quasar unmounts it -- see
            // _agent_get_state's own dialog_open definition for why
            // 'q-dialog--modal' (swapped for '--seamless' the instant a close
            // starts, well before the node's size/attachment change) is the
            // reliable signal, not isVisible alone. Every dialog-scoping site
            // in this module must agree with that definition, or a caller can
            // act on a control it wrongly believes is still covered by a
            // dialog that is, in truth, already closing.
            let root;
            if (scopeId !== null) {{
                root = document.querySelector('[data-agent-id="' + scopeId + '"]');
                if (!root) return {{ok: false, error: 'scope_not_found', scope_id: scopeId}};
            }} else {{
                const dialogs = [...document.querySelectorAll('.q-dialog')]
                    .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
                root = dialogs.length ? dialogs[dialogs.length - 1] : document;
            }}

            const toggles = [...root.querySelectorAll('.q-toggle, .q-checkbox')].filter(isVisible);
            const toggleScore = el => {{
                const t = norm(el.textContent);
                if (t === target) return 2;
                if (t.includes(target)) return 1;
                return 0;
            }};
            const toggleScored = toggles.map(el => ({{el, score: toggleScore(el)}})).filter(c => c.score > 0);
            let toggleMatches = [];
            if (toggleScored.length) {{
                const best = Math.max(...toggleScored.map(c => c.score));
                toggleMatches = toggleScored.filter(c => c.score === best).map(c => c.el);
            }}
            if (toggleMatches.length > 1) {{
                return {{ok: false, error: 'ambiguous', kind: 'toggle', matched_count: toggleMatches.length}};
            }}
            if (toggleMatches.length === 1) {{
                const el = toggleMatches[0];
                if (el.classList.contains('disabled') || el.getAttribute('aria-disabled') === 'true') {{
                    return {{ok: false, error: 'disabled', kind: 'toggle'}};
                }}
                const checked = el.getAttribute('aria-checked') === 'true';
                const want = {str(value).strip().lower() in ('true', '1', 'on', 'yes')!r};
                if (checked !== want) el.click();
                return {{ok: true, kind: 'toggle', changed: checked !== want}};
            }}

            const fields = [...root.querySelectorAll('.q-field')].filter(isVisible);
            const fieldMatches = fields.filter(f => {{
                const lab = f.querySelector('.q-field__label');
                return lab && norm(lab.textContent).includes(target);
            }});
            if (fieldMatches.length > 1) {{
                return {{ok: false, error: 'ambiguous', kind: 'field', matched_count: fieldMatches.length}};
            }}
            if (fieldMatches.length === 0) return {{ok: false, error: 'not_found'}};
            const field = fieldMatches[0];
            if (field.classList.contains('q-field--disabled')) return {{ok: false, error: 'disabled', kind: 'field'}};
            // A plain ui.select() with no use-input prop still renders a
            // native <input> for its display text/a11y, even with no typing
            // UI at all, but it's readonly: Quasar's real selection lives in
            // its own Vue
            // state, not the DOM value, so writing to it directly (as the
            // plain-input path below does) silently no-ops -- the input's
            // .value changes but the rendered/bound selection never does.
            // Readonly inputs must take the click-to-open+pick-menu-item
            // path instead, same as a select with no input element at all.
            const input = field.querySelector('input, textarea');
            if (input && !input.readOnly) {{
                const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(input, {str(value)!r});
                input.dispatchEvent(new Event('input', {{bubbles: true}}));
                input.dispatchEvent(new Event('change', {{bubbles: true}}));
                input.dispatchEvent(new Event('blur', {{bubbles: true}}));
                return {{ok: true, kind: 'input'}};
            }}
            // If a prior _agent_toggle_dropdown call already opened this
            // exact menu, clicking the field again would close it (Quasar's
            // click toggles an already-open select shut, same as a native
            // <select>) instead of (re)opening it -- composing
            // toggle_dropdown -> set_field to pick from a dropdown left open
            // for inspection would otherwise always fail. Skip the click
            // when a menu is already open and go straight to the
            // scroll/pick steps below against it.
            const menu = document.querySelector('.q-menu');
            if (!menu || !isVisible(menu)) field.click();
            return {{ok: true, kind: 'select_opening'}};
        }})()
    """
    try:
        result = await client.run_javascript(detect_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not isinstance(result, dict):
        return {'ok': False, 'error': 'js_error'}
    if result.get('kind') != 'select_opening':
        return result

    await asyncio.sleep(0.3)
    scroll_top_js = """
        (() => {
            const menu = document.querySelector('.q-menu');
            if (menu) menu.scrollTop = 0;
            return null;
        })()
    """
    try:
        await client.run_javascript(scroll_top_js, timeout=5.0)
    except Exception:
        pass
    await asyncio.sleep(0.12)
    option_target = str(value).strip().lower()
    pick_js = f"""
        (() => {{
            const norm = s => (s || '').trim().toLowerCase();
            const target = {option_target!r};
            const items = [...document.querySelectorAll('.q-menu .q-item, .q-menu [role="option"]')]
                .filter(i => !!(i.offsetWidth || i.offsetHeight || i.getClientRects().length));
            const exact = items.find(i => norm(i.textContent) === target);
            const partial = items.filter(i => norm(i.textContent).includes(target));
            const chosen = exact || (partial.length === 1 ? partial[0] : null);
            if (chosen) {{
                chosen.click();
                return {{ok: true, kind: 'select', text: chosen.textContent.trim().slice(0, 60)}};
            }}
            if (partial.length > 1) {{
                return {{ok: false, error: 'ambiguous', kind: 'select', matched_count: partial.length,
                          candidates: partial.map(i => i.textContent.trim().slice(0, 60))}};
            }}
            return {{ok: false, error: 'no_match_yet',
                      rendered: items.map(i => i.textContent.trim().slice(0, 60))}};
        }})()
    """
    scroll_js = """
        (() => {
            const menu = document.querySelector('.q-menu');
            if (!menu) return {can_scroll: false};
            const before = menu.scrollTop;
            menu.scrollTop = before + menu.clientHeight;
            return {can_scroll: menu.scrollTop > before};
        })()
    """
    # Option texts seen while scrolling the menu, reported when the option is not found.
    seen_rendered: set[str] = set()
    # Try the rendered options, then scroll the menu one page and retry, at most 40 pages.
    for _ in range(40):
        try:
            picked = await client.run_javascript(pick_js, timeout=5.0)
        except Exception as exc:
            return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
        if not isinstance(picked, dict):
            return {'ok': False, 'error': 'js_error'}
        if picked.get('error') != 'no_match_yet':
            return picked
        seen_rendered.update(picked.get('rendered', []))
        try:
            scrolled = await client.run_javascript(scroll_js, timeout=5.0)
        except Exception as exc:
            return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
        if not isinstance(scrolled, dict) or not scrolled.get('can_scroll'):
            break
        await asyncio.sleep(0.12)

    close_js = """
        (() => {
            const card = document.querySelector('.q-dialog .q-card');
            if (card) card.click();
        })()
    """
    try:
        await client.run_javascript(close_js, timeout=5.0)
    except Exception:
        pass
    return {'ok': False, 'error': 'option_not_found', 'kind': 'select',
            'rendered_options_seen': sorted(seen_rendered)[:50]}


async def _agent_toggle_dropdown(client: Client, label: str, scope_id: Optional[str] = None) -> dict:
    """Open a select's menu, or close it if it is open.

    Closing goes through the QSelect's hidePopup() because synthetic events do not close a Quasar menu.

    Args:
        client (Client): Target browser tab.
        label (str): Label text of the select.
        scope_id (str, optional): data-agent-id of an element to search within.

    Returns:
        dict: {'ok': True, 'action': 'opened' | 'closed', 'is_open': bool} or {'ok': False, 'error': ...} (not_found, ambiguous, disabled, not_a_dropdown, scope_not_found, qselect_ref_not_found).
    """

    scope_id_js = json.dumps(scope_id)
    find_js = f"""
        (() => {{
            const target = {label!r}.trim().toLowerCase();
            const scopeId = {scope_id_js};
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const norm = s => (s || '').trim().toLowerCase();
            let root;
            if (scopeId !== null) {{
                root = document.querySelector('[data-agent-id="' + scopeId + '"]');
                if (!root) return {{ok: false, error: 'scope_not_found', scope_id: scopeId}};
            }} else {{
                const dialogs = [...document.querySelectorAll('.q-dialog')]
                    .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
                root = dialogs.length ? dialogs[dialogs.length - 1] : document;
            }}
            const fields = [...root.querySelectorAll('.q-field')].filter(isVisible);
            const fieldMatches = fields.filter(f => {{
                const lab = f.querySelector('.q-field__label');
                return lab && norm(lab.textContent).includes(target);
            }});
            if (fieldMatches.length > 1) return {{ok: false, error: 'ambiguous', matched_count: fieldMatches.length}};
            if (fieldMatches.length === 0) return {{ok: false, error: 'not_found'}};
            const field = fieldMatches[0];
            if (field.classList.contains('q-field--disabled')) return {{ok: false, error: 'disabled'}};
            const input = field.querySelector('input, textarea');
            if (input && !input.readOnly) return {{ok: false, error: 'not_a_dropdown'}};

            const menu = document.querySelector('.q-menu');
            const menuOpen = !!menu && isVisible(menu);
            if (menuOpen) {{
                // Synthetic DOM events (click, Escape keydown, outside
                // mousedown/click, native blur) all no-op against this
                // QMenu: Quasar's own popup-visibility handlers only react
                // to trusted (real, OS-generated) events, which anything
                // dispatched here never is. Going through NiceGUI's own ref
                // registry instead -- the same one its run_method() RPC
                // uses server-side (see nicegui.js's runMethod/getElement)
                // -- reaches QSelect's public hidePopup() directly as a
                // plain method call, with no event/trust involved at all.
                // NiceGUI's own id ("c<N>") isn't on the .q-field root or
                // the <input> (both carry Quasar-internal ids instead) --
                // it's on another node inside this field's subtree, which
                // is enough to key into mounted_app.$refs the same way
                // nicegui.js's own runMethod()/getElement() do.
                const idEl = field.querySelector('[id^="c"]');
                const fieldId = idEl ? idEl.id.replace(/^c/, '') : '';
                const vueEl = fieldId ? mounted_app.$refs['r' + fieldId] : null;
                const qSelect = vueEl && vueEl.$refs && vueEl.$refs.qRef;
                if (qSelect && typeof qSelect.hidePopup === 'function') {{
                    qSelect.hidePopup();
                    return {{ok: true, action: 'closing'}};
                }}
                return {{
                    ok: false, error: 'qselect_ref_not_found',
                    diag: {{fieldId, hasVueEl: !!vueEl, hasQRef: !!qSelect}},
                }};
            }}
            field.click();
            return {{ok: true, action: 'opening'}};
        }})()
    """
    try:
        result = await client.run_javascript(find_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not isinstance(result, dict):
        return {'ok': False, 'error': 'js_error'}
    if not result.get('ok'):
        return result

    await asyncio.sleep(0.3)
    check_js = """
        (() => {
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const menu = document.querySelector('.q-menu');
            return {is_open: !!menu && isVisible(menu)};
        })()
    """
    try:
        checked = await client.run_javascript(check_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    is_open = bool(isinstance(checked, dict) and checked.get('is_open'))
    action = 'opened' if result['action'] == 'opening' else 'closed'
    out = {'ok': True, 'action': action, 'is_open': is_open}
    if 'diag' in result:
        out['diag'] = result['diag']
    return out


async def _agent_read_dropdown_options(client: Client, label: str, scope_id: Optional[str] = None) -> dict:
    """List the options of a select whose menu is already open.

    Scrolls the menu to the top, then page by page (at most 40 pages), collecting option texts.

    Args:
        client (Client): Target browser tab.
        label (str): Label text of the select.
        scope_id (str, optional): data-agent-id of an element to search within.

    Returns:
        dict: {'ok': True, 'options': [{'text': str, 'selected': bool}, ...]} or {'ok': False, 'error': ...} (not_found, ambiguous, disabled, not_open, scope_not_found).
    """

    scope_id_js = json.dumps(scope_id)
    find_js = f"""
        (() => {{
            const target = {label!r}.trim().toLowerCase();
            const scopeId = {scope_id_js};
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const norm = s => (s || '').trim().toLowerCase();
            let root;
            if (scopeId !== null) {{
                root = document.querySelector('[data-agent-id="' + scopeId + '"]');
                if (!root) return {{ok: false, error: 'scope_not_found', scope_id: scopeId}};
            }} else {{
                const dialogs = [...document.querySelectorAll('.q-dialog')]
                    .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
                root = dialogs.length ? dialogs[dialogs.length - 1] : document;
            }}
            const fields = [...root.querySelectorAll('.q-field')].filter(isVisible);
            const fieldMatches = fields.filter(f => {{
                const lab = f.querySelector('.q-field__label');
                return lab && norm(lab.textContent).includes(target);
            }});
            if (fieldMatches.length > 1) return {{ok: false, error: 'ambiguous', matched_count: fieldMatches.length}};
            if (fieldMatches.length === 0) return {{ok: false, error: 'not_found'}};
            const field = fieldMatches[0];
            if (field.classList.contains('q-field--disabled')) return {{ok: false, error: 'disabled'}};

            const menu = document.querySelector('.q-menu');
            if (!menu || !isVisible(menu)) return {{ok: false, error: 'not_open'}};
            return {{ok: true}};
        }})()
    """
    try:
        result = await client.run_javascript(find_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not isinstance(result, dict):
        return {'ok': False, 'error': 'js_error'}
    if not result.get('ok'):
        return result

    scroll_top_js = """
        (() => {
            const menu = document.querySelector('.q-menu');
            if (menu) menu.scrollTop = 0;
            return null;
        })()
    """
    try:
        await client.run_javascript(scroll_top_js, timeout=5.0)
    except Exception:
        pass
    await asyncio.sleep(0.12)

    collect_js = """
        (() => {
            const items = [...document.querySelectorAll('.q-menu .q-item, .q-menu [role="option"]')]
                .filter(i => !!(i.offsetWidth || i.offsetHeight || i.getClientRects().length));
            return items.map(i => ({
                text: i.textContent.trim().slice(0, 60),
                selected: i.getAttribute('aria-selected') === 'true' || i.classList.contains('q-item--active'),
            }));
        })()
    """
    scroll_js = """
        (() => {
            const menu = document.querySelector('.q-menu');
            if (!menu) return {can_scroll: false};
            const before = menu.scrollTop;
            menu.scrollTop = before + menu.clientHeight;
            return {can_scroll: menu.scrollTop > before};
        })()
    """
    seen: dict[str, bool] = {}
    for _ in range(40):
        try:
            batch = await client.run_javascript(collect_js, timeout=5.0)
        except Exception as exc:
            return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
        if isinstance(batch, list):
            for item in batch:
                if isinstance(item, dict) and item.get('text'):
                    seen[item['text']] = seen.get(item['text'], False) or bool(item.get('selected'))
        try:
            scrolled = await client.run_javascript(scroll_js, timeout=5.0)
        except Exception as exc:
            return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
        if not isinstance(scrolled, dict) or not scrolled.get('can_scroll'):
            break
        await asyncio.sleep(0.12)

    return {'ok': True, 'options': [{'text': text, 'selected': sel} for text, sel in seen.items()]}


async def _agent_get_state(client: Client) -> dict:
    """Snapshot the visible UI of a tab.

    Args:
        client (Client): Target browser tab.

    Returns:
        dict: 'dialog_open', 'drawer' (right drawer open flag and rect, or None), lists of visible 'buttons', 'toggles', 'fields' (label, value, kind) and 'tabs', and 'sources' (each benchmark source's latest metrics); or an error dict.
    """

    js = """
        (() => {
            // offsetParent is unreliable here: Chromium reports it as null for
            // any position:fixed element regardless of whether it's actually
            // shown, and Quasar's dialogs/menus are position:fixed.
            // offsetWidth/offsetHeight/getClientRects() all correctly read 0
            // for a genuinely display:none-hidden element without that false
            // negative.
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const isDisabled = el => !!(el.disabled || el.getAttribute('aria-disabled') === 'true'
                                         || el.classList.contains('disabled') || el.classList.contains('q-btn--disable'));
            const iconOf = el => {
                const icon = el.querySelector('i.material-icons, i.q-icon');
                return icon ? icon.textContent.trim() : null;
            };
            // A dialog mid-close is still "visible" by the offsetWidth/
            // offsetHeight/getClientRects check above: closing one of this
            // app's dialogs keeps its .q-dialog node laid out with real
            // size, and even still attached to the DOM, for a brief window
            // after the close is triggered, before Quasar finally unmounts
            // it -- so a dialog.close() that's genuinely in flight would
            // read as dialog_open: true for that whole window, which could
            // cause a caller to act on a page control it wrongly believed
            // was still covered. What *does* change the instant a close is
            // triggered, well before the node's size or DOM attachment
            // change, is Quasar swapping the dialog's own 'q-dialog--modal'
            // class for 'q-dialog--seamless' -- no dialog in this app is
            // ever opened in seamless mode (nothing sets that prop), so
            // '--modal' is reliably present throughout a dialog's real open
            // lifetime and reliably gone the instant a close starts, well
            // before the node disappears.
            const dialogs = [...document.querySelectorAll('.q-dialog')]
                .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
            // The Advanced Settings drawer (Benchmarking tab only) never
            // toggles display/visibility when it opens/closes -- Quasar
            // slides it on/off-screen via a CSS transform instead (open ->
            // transform: translateX(0px), rect flush with the viewport's
            // right edge; closed -> translated fully off past the right
            // edge) -- so plain isVisible() can't tell the
            // two apart; a closed drawer's rect still has nonzero size, just
            // positioned outside the viewport. Whether its rect still
            // intersects the viewport at all is a cheap, reliable stand-in
            // for parsing the transform matrix directly.
            const rightDrawer = document.querySelector('.q-drawer--right');
            let drawer = null;
            if (rightDrawer) {
                const rect = rightDrawer.getBoundingClientRect();
                drawer = {
                    open: rect.right > 0 && rect.left < window.innerWidth,
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                };
            }
            const buttons = [];
            document.querySelectorAll('button, .q-btn').forEach(el => {
                if (!isVisible(el)) return;
                buttons.push({
                    text: el.textContent.trim().slice(0, 60),
                    icon: iconOf(el),
                    disabled: isDisabled(el),
                    in_dialog: !!el.closest('.q-dialog'),
                });
            });
            const toggles = [];
            document.querySelectorAll('.q-toggle, .q-checkbox').forEach(el => {
                if (!isVisible(el)) return;
                let label = el.textContent.trim();
                if (!label) {
                    // Same self-match pitfall as _agent_click's labelsFor:
                    // el's own root carries Quasar's ".row" utility class.
                    const row = el.parentElement ? el.parentElement.closest('.row') : null;
                    if (row) label = row.textContent.trim();
                }
                toggles.push({
                    label: label.slice(0, 60),
                    checked: el.getAttribute('aria-checked') === 'true',
                    disabled: isDisabled(el),
                    in_dialog: !!el.closest('.q-dialog'),
                });
            });
            const fields = [];
            document.querySelectorAll('.q-field').forEach(el => {
                if (!isVisible(el)) return;
                const labelEl = el.querySelector('.q-field__label');
                const input = el.querySelector('input, textarea');
                const nativeText = el.querySelector('.q-field__native');
                fields.push({
                    label: labelEl ? labelEl.textContent.trim().slice(0, 60) : null,
                    value: input ? input.value : (nativeText ? nativeText.textContent.trim() : null),
                    // A q-select renders a readonly native <input> for its
                    // display text (see _agent_set_field's own note on this) --
                    // without the readOnly check this misreports every select
                    // as a plain text field, which is indistinguishable from a
                    // genuinely empty/broken one to anything reading get_state.
                    kind: input ? (input.readOnly ? 'select' : (input.type || 'text')) : 'select',
                    disabled: el.classList.contains('q-field--disabled'),
                    in_dialog: !!el.closest('.q-dialog'),
                });
            });
            const tabs = [];
            document.querySelectorAll('.q-tab').forEach(el => {
                if (!isVisible(el)) return;
                tabs.push({
                    text: el.textContent.trim().slice(0, 40),
                    active: el.classList.contains('q-tab--active'),
                });
            });
            return {dialog_open: dialogs.length > 0, drawer, buttons, toggles, fields, tabs};
        })()
    """
    try:
        result = await client.run_javascript(js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not isinstance(result, dict):
        return {'ok': False, 'error': 'js_error'}
    result['sources'] = {
        source_id: dict(entry.get('latest_metrics') or {})
        for source_id, entry in BENCHMARK_SOURCES.items()
    }
    return result


async def _agent_get_text(client: Client, contains: str) -> dict:
    """Return the text of the single visible leaf element containing a substring.

    Searches the topmost modal dialog, or the whole page when none is open.

    Args:
        client (Client): Target browser tab.
        contains (str): Case-insensitive substring.

    Returns:
        dict: {'ok': True, 'text': ...} or {'ok': False, 'error': 'not_found' | 'ambiguous', ...}.
    """
    js = f"""
        (() => {{
            const target = {contains!r}.trim().toLowerCase();
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const norm = s => (s || '').trim().toLowerCase();
            // A dialog mid-close still reads as isVisible (nonzero size, still
            // attached) for a brief window before Quasar unmounts it -- see
            // _agent_get_state's own dialog_open definition for why
            // 'q-dialog--modal' (swapped for '--seamless' the instant a close
            // starts, well before the node's size/attachment change) is the
            // reliable signal, not isVisible alone. Every dialog-scoping site
            // in this module must agree with that definition, or a caller can
            // act on a control it wrongly believes is still covered by a
            // dialog that is, in truth, already closing.
            const dialogs = [...document.querySelectorAll('.q-dialog')]
                .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
            const scope = dialogs.length ? dialogs[dialogs.length - 1] : document;
            // Leaf-most match only: an ancestor's textContent also includes
            // its descendants' text, which would make every match "ambiguous"
            // against its own parents -- so discard a candidate that contains
            // another candidate.
            const all = [...scope.querySelectorAll('*')]
                .filter(el => el.children.length === 0 && isVisible(el) && norm(el.textContent).includes(target));
            if (all.length === 0) return {{ok: false, error: 'not_found'}};
            if (all.length > 1) return {{ok: false, error: 'ambiguous', matched_count: all.length}};
            return {{ok: true, text: all[0].textContent.trim()}};
        }})()
    """
    try:
        result = await client.run_javascript(js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    return result if isinstance(result, dict) else {'ok': False, 'error': 'js_error'}


async def _agent_get_tooltip(client: Client, label: str) -> dict:
    """Hover an element and read its tooltip.

    Dispatches enter events, waits 0.4 s, reads the visible tooltip and sends leave events.

    Args:
        client (Client): Target browser tab.
        label (str): Substring of the element's text; interactive controls are tried first, then leaf text elements.

    Returns:
        dict: {'ok': True, 'text': ...}, or {'ok': False, ...} when not found, ambiguous or no non-empty tooltip appeared.
    """
    first_js = f"""
        (() => {{
            const target = {label!r}.trim().toLowerCase();
            // offsetParent is unreliable here: Chromium reports it as null for
            // any position:fixed element regardless of whether it's actually
            // shown, and Quasar's dialogs/menus are position:fixed.
            // offsetWidth/offsetHeight/getClientRects() all correctly read 0
            // for a genuinely display:none-hidden element without that false
            // negative.
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const norm = s => (s || '').trim().toLowerCase();
            let candidates = [...document.querySelectorAll('button, .q-btn, .q-field, .q-toggle, .q-checkbox, .q-tab, label')]
                .filter(el => isVisible(el) && norm(el.textContent).includes(target));
            if (candidates.length === 0) {{
                // Fall back to a plain leaf text element (e.g. a ui.label,
                // which NiceGUI renders as a <div>/<span>, not an HTML
                // <label>) -- the same leaf-most matching _agent_get_text
                // uses, since the explicit widget list above only covers
                // genuinely interactive controls.
                candidates = [...document.querySelectorAll('*')]
                    .filter(el => el.children.length === 0 && isVisible(el) && norm(el.textContent).includes(target));
            }}
            if (candidates.length === 0) return {{ok: false, error: 'not_found'}};
            if (candidates.length > 1) return {{ok: false, error: 'ambiguous', matched_count: candidates.length}};
            const el = candidates[0];
            const rect = el.getBoundingClientRect();
            const opts = {{bubbles: true, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2}};
            el.dispatchEvent(new MouseEvent('pointerenter', opts));
            el.dispatchEvent(new MouseEvent('mouseenter', opts));
            el.dispatchEvent(new MouseEvent('mouseover', opts));
            window.__agentTooltipTarget = el;
            return {{ok: true, pending: true}};
        }})()
    """
    try:
        first = await client.run_javascript(first_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not isinstance(first, dict) or not first.get('ok'):
        return first if isinstance(first, dict) else {'ok': False, 'error': 'js_error'}

    await asyncio.sleep(0.4)
    read_js = """
        (() => {
            // Quasar can leave earlier .q-tooltip nodes mounted-but-hidden
            // in the DOM rather than removing them, so the first querySelector
            // match is NOT reliable -- must find one that's actually visible
            // right now, and treat a visible-but-blank tooltip as "no tooltip"
            // too (an empty string tells an agent nothing a null doesn't).
            // Not offsetParent -- Quasar tooltips are position:fixed
            // (teleported), which Chromium always reports as offsetParent
            // null regardless of real visibility. See the isVisible note
            // further up this module.
            const tip = [...document.querySelectorAll('.q-tooltip')]
                .find(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const rawText = tip ? tip.textContent.trim() : '';
            const text = rawText ? rawText : null;
            const el = window.__agentTooltipTarget;
            if (el) {
                el.dispatchEvent(new MouseEvent('mouseleave', {bubbles: true}));
                el.dispatchEvent(new MouseEvent('pointerleave', {bubbles: true}));
                window.__agentTooltipTarget = null;
            }
            return {ok: text !== null, text};
        })()
    """
    try:
        result = await client.run_javascript(read_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    return result if isinstance(result, dict) else {'ok': False, 'error': 'js_error'}


def _agent_find_element(client: Client, element_type: type):
    """Find the NiceGUI element of a type that belongs to what the user currently sees.

    Prefers the most recently created element inside an open dialog, then one outside any dialog, then the most recently created one.

    Args:
        client (Client): Browser tab whose elements are searched.
        element_type (type): Element class to look for.

    Returns:
        The element, or None if the client has none of that type.
    """

    matches = [el for el in reversed(list(client.elements.values())) if isinstance(el, element_type)]
    if not matches:
        return None

    def open_dialog_ancestor(el):
        """Return the open ui.dialog ancestor of an element, or None."""
        return next((a for a in el.ancestors() if isinstance(a, ui.dialog) and a.value), None)

    for el in matches:
        if open_dialog_ancestor(el) is not None:
            return el
    for el in matches:
        has_any_dialog_ancestor = any(isinstance(a, ui.dialog) for a in el.ancestors())
        if not has_any_dialog_ancestor:
            return el
    return matches[0]


def _agent_get_graph(client: Client) -> dict:
    """Return the canvas graph of a tab.

    Args:
        client (Client): Target browser tab.

    Returns:
        dict: {'nodes': [...], 'edges': [...]} from the tab's PipelineFlow (the ROI subflow's graph while its dialog is open), or the shared current graph when the tab has no canvas.
    """
    client_flow = _agent_find_element(client, PipelineFlow)
    if client_flow is None:
        return {'nodes': current_graph['nodes'], 'edges': current_graph['edges']}
    return {'nodes': client_flow.agent_nodes, 'edges': client_flow.agent_edges}


def _agent_build_node_label_map() -> dict:
    """Map palette leaf labels to catalog entries.

    Returns:
        dict: Leaf label -> (NODE_CATALOG key, category label), for leaves present in NODE_CATALOG.
    """
    out: dict = {}
    for group in PALETTE_TREE:
        for category in group.get('children', []):
            for leaf in category.get('children', []):
                if leaf['id'] in NODE_CATALOG:
                    out[leaf['label']] = (leaf['id'], category['label'])
    return out


AGENT_NODE_LABEL_MAP = _agent_build_node_label_map()


async def _agent_add_node(client: Client, label: str) -> dict:
    """Add a node by clicking its leaf in the palette tree.

    Expands the leaf's category first when the leaf is not visible, then waits up to 5 s for the node '<catalog key>-<counter + 1>' to appear in the graph.

    Args:
        client (Client): Target browser tab.
        label (str): Exact palette leaf label.

    Returns:
        dict: {'ok': True, 'node_id': ..., 'position': ...} or {'ok': False, 'error': ...} (unknown_label with 'known_labels', category_not_found, leaf_not_found_after_expand, node_never_appeared, js_exception).
    """
    entry = AGENT_NODE_LABEL_MAP.get(label)
    if entry is None:
        return {'ok': False, 'error': 'unknown_label', 'known_labels': sorted(AGENT_NODE_LABEL_MAP)}
    _catalog_key, category_label = entry
    expected_id = f'{_catalog_key}-{core.app.state.node_counter + 1}'

    click_js = f"""
        (() => {{
            const el = [...document.querySelectorAll(".q-tree__node-header-content > div")]
                .find(el => el.textContent.trim() === {label!r});
            if (!el) return false;
            el.click();
            return true;
        }})()
    """
    try:
        clicked = await client.run_javascript(click_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}

    if not clicked:
        expand_js = f"""
            (() => {{
                const headers = [...document.querySelectorAll('.q-tree__node-header')];
                const header = headers.find(h => {{
                    const labelDiv = h.querySelector('.q-tree__node-header-content > div');
                    return labelDiv && labelDiv.textContent.trim() === {category_label!r};
                }});
                if (!header) return false;
                const arrow = header.querySelector('.q-tree__arrow');
                if (!arrow) return false;
                arrow.click();
                return true;
            }})()
        """
        try:
            expanded = await client.run_javascript(expand_js, timeout=5.0)
        except Exception as exc:
            return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
        if not expanded:
            return {'ok': False, 'error': 'category_not_found', 'category': category_label}
        await asyncio.sleep(0.3)
        try:
            clicked = await client.run_javascript(click_js, timeout=5.0)
        except Exception as exc:
            return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
        if not clicked:
            return {'ok': False, 'error': 'leaf_not_found_after_expand', 'label': label}

    # Poll up to 5 s for the node to reach the shared graph.
    for _ in range(50):
        node = next((n for n in current_graph['nodes'] if n['id'] == expected_id), None)
        if node is not None:
            return {'ok': True, 'node_id': expected_id, 'position': node['position']}
        await asyncio.sleep(0.1)
    return {'ok': False, 'error': 'node_never_appeared', 'expected_id': expected_id}


async def _agent_position_node(client: Client, node_id: str, frac_x: float, frac_y: float) -> dict:
    """Move a node to a point given as fractions of the canvas pane, animating the drag.

    Args:
        client (Client): Target browser tab.
        node_id (str): Id of the node.
        frac_x (float): Horizontal position, 0.0 to 1.0 of the pane width.
        frac_y (float): Vertical position, 0.0 to 1.0 of the pane height.

    Returns:
        dict: {'ok': True, 'node_id': ..., 'position': ...} or {'ok': False, 'error': ...} (out_of_range, canvas_not_found, node_not_found, node_not_rendered, node_disappeared, js_exception).
    """
    if not (0.0 <= frac_x <= 1.0 and 0.0 <= frac_y <= 1.0):
        return {'ok': False, 'error': 'out_of_range', 'detail': 'frac_x/frac_y must be within [0.0, 1.0]'}

    client_flow = _agent_find_element(client, PipelineFlow)
    if client_flow is None:
        return {'ok': False, 'error': 'canvas_not_found'}

    if not any(n['id'] == node_id for n in client_flow.agent_nodes):
        return {'ok': False, 'error': 'node_not_found', 'node_id': node_id}

    rect_js = """
        (() => {
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            // A dialog mid-close still reads as isVisible (nonzero size, still
            // attached) for a brief window before Quasar unmounts it -- see
            // _agent_get_state's own dialog_open definition for why
            // 'q-dialog--modal' (swapped for '--seamless' the instant a close
            // starts, well before the node's size/attachment change) is the
            // reliable signal, not isVisible alone. Every dialog-scoping site
            // in this module must agree with that definition, or a caller can
            // act on a control it wrongly believes is still covered by a
            // dialog that is, in truth, already closing.
            const dialogs = [...document.querySelectorAll('.q-dialog')]
                .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
            const root = dialogs.length ? dialogs[dialogs.length - 1] : document;
            const el = root.querySelector('.vue-flow__pane');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        })()
    """
    node_pos_js = f"""
        (() => {{
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            // A dialog mid-close still reads as isVisible (nonzero size, still
            // attached) for a brief window before Quasar unmounts it -- see
            // _agent_get_state's own dialog_open definition for why
            // 'q-dialog--modal' (swapped for '--seamless' the instant a close
            // starts, well before the node's size/attachment change) is the
            // reliable signal, not isVisible alone. Every dialog-scoping site
            // in this module must agree with that definition, or a caller can
            // act on a control it wrongly believes is still covered by a
            // dialog that is, in truth, already closing.
            const dialogs = [...document.querySelectorAll('.q-dialog')]
                .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
            const root = dialogs.length ? dialogs[dialogs.length - 1] : document;
            const el = root.querySelector('.vue-flow__node[data-id="{node_id}"]');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
        }})()
    """
    try:
        canvas_rect = await client.run_javascript(rect_js, timeout=5.0)
        node_pos = await client.run_javascript(node_pos_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not canvas_rect:
        return {'ok': False, 'error': 'canvas_not_found'}
    if not node_pos:
        return {'ok': False, 'error': 'node_not_rendered', 'node_id': node_id}

    target_x = canvas_rect['x'] + canvas_rect['width'] * frac_x
    target_y = canvas_rect['y'] + canvas_rect['height'] * frac_y
    # Move the node in 18 steps over 0.35 s.
    steps, total_duration = 18, 0.35
    step_duration = total_duration / steps
    for step in range(1, steps + 1):
        frac = step / steps
        x = node_pos['x'] + (target_x - node_pos['x']) * frac
        y = node_pos['y'] + (target_y - node_pos['y']) * frac
        client_flow.move_node(node_id, x, y)
        await asyncio.sleep(step_duration)
    await asyncio.sleep(0.15)

    final = next((n for n in client_flow.agent_nodes if n['id'] == node_id), None)
    if final is None:
        return {'ok': False, 'error': 'node_disappeared', 'node_id': node_id}
    return {'ok': True, 'node_id': node_id, 'position': final['position']}


async def _agent_connect_nodes(client: Client, source_id: str, target_id: str) -> dict:
    """Connect two nodes and wait up to 3 s for the edge to appear.

    Refused on an ROI subflow canvas, whose wiring is fixed.

    Args:
        client (Client): Target browser tab.
        source_id (str): Source node id.
        target_id (str): Target node id.

    Returns:
        dict: {'ok': True, 'source': ..., 'target': ...} or {'ok': False, 'error': ...} (canvas_not_found, subflow_locked, node_not_found, edge_never_appeared).
    """

    client_flow = _agent_find_element(client, PipelineFlow)
    if client_flow is None:
        return {'ok': False, 'error': 'canvas_not_found'}

    if client_flow.agent_scope == 'roi_subflow':
        return {'ok': False, 'error': 'subflow_locked', 'detail': 'ROI subflow wiring is fixed and cannot be rewired'}

    node_ids = {n['id'] for n in client_flow.agent_nodes}
    missing = [nid for nid in (source_id, target_id) if nid not in node_ids]
    if missing:
        return {'ok': False, 'error': 'node_not_found', 'missing': missing}

    client_flow.connect_nodes(source_id, target_id)

    # Poll up to 3 s for the edge to appear.
    for _ in range(30):
        if any(e['source'] == source_id and e['target'] == target_id for e in client_flow.agent_edges):
            return {'ok': True, 'source': source_id, 'target': target_id}
        await asyncio.sleep(0.1)
    return {'ok': False, 'error': 'edge_never_appeared', 'source': source_id, 'target': target_id}


async def _agent_delete_node(client: Client, node_id: str) -> dict:
    """Delete a node and wait up to 3 s for it to disappear.

    Args:
        client (Client): Target browser tab.
        node_id (str): Id of the node.

    Returns:
        dict: {'ok': True, 'node_id': ...} or {'ok': False, 'error': ...} (canvas_not_found, node_not_found, node_locked, node_still_present).
    """
    client_flow = _agent_find_element(client, PipelineFlow)
    if client_flow is None:
        return {'ok': False, 'error': 'canvas_not_found'}

    node = next((n for n in client_flow.agent_nodes if n['id'] == node_id), None)
    if node is None:
        return {'ok': False, 'error': 'node_not_found', 'node_id': node_id}
    if (node.get('data') or {}).get('locked'):
        return {'ok': False, 'error': 'node_locked', 'node_id': node_id}

    client_flow.delete_node(node_id)

    # Poll up to 3 s for the node to disappear.
    for _ in range(30):
        if not any(n['id'] == node_id for n in client_flow.agent_nodes):
            return {'ok': True, 'node_id': node_id}
        await asyncio.sleep(0.1)
    return {'ok': False, 'error': 'node_still_present', 'node_id': node_id}


async def _agent_delete_edge(client: Client, source_id: str, target_id: str) -> dict:
    """Delete the edge between two nodes and wait up to 3 s for it to disappear.

    Args:
        client (Client): Target browser tab.
        source_id (str): Source node id.
        target_id (str): Target node id.

    Returns:
        dict: {'ok': True, 'source': ..., 'target': ...} or {'ok': False, 'error': ...} (canvas_not_found, edge_not_found, edge_still_present).
    """
    client_flow = _agent_find_element(client, PipelineFlow)
    if client_flow is None:
        return {'ok': False, 'error': 'canvas_not_found'}

    edge = next((e for e in client_flow.agent_edges if e['source'] == source_id and e['target'] == target_id), None)
    if edge is None:
        return {'ok': False, 'error': 'edge_not_found', 'source': source_id, 'target': target_id}

    client_flow.delete_edge(edge['id'])

    # Poll up to 3 s for the edge to disappear.
    for _ in range(30):
        if not any(e['id'] == edge['id'] for e in client_flow.agent_edges):
            return {'ok': True, 'source': source_id, 'target': target_id}
        await asyncio.sleep(0.1)
    return {'ok': False, 'error': 'edge_still_present', 'source': source_id, 'target': target_id}


async def _agent_open_node(client: Client, node_id: str) -> dict:
    """Open a node's dialog by double-clicking it, waiting up to 5 s for a new modal dialog.

    Args:
        client (Client): Target browser tab.
        node_id (str): Id of the node.

    Returns:
        dict: {'ok': True, 'node_id': ...} or {'ok': False, 'error': ...} (canvas_not_found, node_not_found, node_not_rendered, dialog_never_opened, js_exception).
    """

    client_flow = _agent_find_element(client, PipelineFlow)
    if client_flow is None:
        return {'ok': False, 'error': 'canvas_not_found'}
    if not any(n['id'] == node_id for n in client_flow.agent_nodes):
        return {'ok': False, 'error': 'node_not_found', 'node_id': node_id}

    visible_dialog_count_js = (
        "[...document.querySelectorAll('.q-dialog')]"
        ".filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)"
        " && el.classList.contains('q-dialog--modal')).length"
    )
    try:
        dialogs_before = await client.run_javascript(visible_dialog_count_js, timeout=3.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}

    dblclick_js = f"""
        (() => {{
            const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            // A dialog mid-close still reads as isVisible (nonzero size, still
            // attached) for a brief window before Quasar unmounts it -- see
            // _agent_get_state's own dialog_open definition for why
            // 'q-dialog--modal' (swapped for '--seamless' the instant a close
            // starts, well before the node's size/attachment change) is the
            // reliable signal, not isVisible alone. Every dialog-scoping site
            // in this module must agree with that definition, or a caller can
            // act on a control it wrongly believes is still covered by a
            // dialog that is, in truth, already closing.
            const dialogs = [...document.querySelectorAll('.q-dialog')]
                .filter(el => isVisible(el) && el.classList.contains('q-dialog--modal'));
            const root = dialogs.length ? dialogs[dialogs.length - 1] : document;
            const el = root.querySelector('.vue-flow__node[data-id="{node_id}"]');
            if (!el) return false;
            el.dispatchEvent(new MouseEvent('dblclick', {{bubbles: true, cancelable: true, view: window}}));
            return true;
        }})()
    """
    try:
        dispatched = await client.run_javascript(dblclick_js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not dispatched:
        return {'ok': False, 'error': 'node_not_rendered', 'node_id': node_id}

    # Poll up to 5 s for a new modal dialog.
    for _ in range(50):
        try:
            dialogs_now = await client.run_javascript(visible_dialog_count_js, timeout=3.0)
        except Exception as exc:
            return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
        if dialogs_now > dialogs_before:
            return {'ok': True, 'node_id': node_id}
        await asyncio.sleep(0.1)
    return {'ok': False, 'error': 'dialog_never_opened', 'node_id': node_id}


def _agent_get_notifications(client_id: str, *, since_id: int = 0) -> list:
    """Return a client's recorded toasts newer than an id.

    Args:
        client_id (str): Id of the browser tab.
        since_id (int, optional): Only notifications with a greater id are returned. Defaults to 0.

    Returns:
        list: Notification records ({'id', 'ts', 'message', 'type', 'position'}), oldest first.
    """
    buf = AGENT_NOTIFICATION_BUFFERS.get(client_id, ())
    return [n for n in buf if n['id'] > since_id]


async def _agent_highlight(
    client: Client,
    kind: str,
    target: Optional[str] = None,
    text: Optional[str] = None,
    *,
    id: Optional[str] = None,
    color: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
) -> dict:
    """Draw a highlight overlay in the tab through window.__annotateHighlight.

    For kind 'edge' the edge between source_id and target_id is looked up and its id becomes the target. Only arguments that are not None are sent.

    Args:
        client (Client): Target browser tab.
        kind (str): Highlight kind (button, tab, toggle, field, node, edge, dialog, text, palette, auto, pointer).
        target (str, optional): What to highlight; meaning depends on kind.
        text (str, optional): Callout text.
        id (str, optional): Id for clearing this highlight later.
        color (str, optional): CSS color.
        x (float, optional): Viewport x fraction for kind 'pointer'.
        y (float, optional): Viewport y fraction for kind 'pointer'.
        source_id (str, optional): Edge source node id (kind 'edge').
        target_id (str, optional): Edge target node id (kind 'edge').

    Returns:
        dict: The overlay's result, or {'ok': False, 'error': ...} (missing_source_or_target, canvas_not_found, edge_not_found, js_exception, js_error).
    """
    if kind == 'edge':
        if source_id is None or target_id is None:
            return {'ok': False, 'error': 'missing_source_or_target'}
        client_flow = _agent_find_element(client, PipelineFlow)
        if client_flow is None:
            return {'ok': False, 'error': 'canvas_not_found'}
        edge = next((e for e in client_flow.agent_edges if e['source'] == source_id and e['target'] == target_id), None)
        if edge is None:
            return {'ok': False, 'error': 'edge_not_found', 'source': source_id, 'target': target_id}
        target = edge['id']

    spec: dict = {'kind': kind}
    if target is not None:
        spec['target'] = target
    if text is not None:
        spec['text'] = text
    if id is not None:
        spec['id'] = id
    if color is not None:
        spec['color'] = color
    if x is not None:
        spec['x'] = x
    if y is not None:
        spec['y'] = y
    js = f'window.__annotateHighlight({json.dumps(spec)})'
    try:
        result = await client.run_javascript(js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    return result if isinstance(result, dict) else {'ok': False, 'error': 'js_error'}


async def _agent_clear_highlight(client: Client, id: Optional[str] = None) -> dict:
    """Remove one highlight, or all of them.

    Args:
        client (Client): Target browser tab.
        id (str, optional): Highlight id; all highlights are cleared when omitted.

    Returns:
        dict: {'ok': True}, or {'ok': False, 'error': 'js_exception', ...}.
    """
    js = f'window.__annotateClear({json.dumps(id)})' if id is not None else 'window.__annotateClearAll()'
    try:
        await client.run_javascript(js, timeout=5.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    return {'ok': True}


async def _agent_screenshot(client: Client, max_width: int = 1280, quality: float = 0.5) -> dict:
    """Capture the page as a JPEG with html2canvas.

    Needs html2canvas loaded in the page. Images with blob: URLs (such as the pinned stream's live frame) cannot be re-fetched by html2canvas, so in the cloned document each is swapped for a canvas painted with the image's current pixels. The result is downscaled to max_width if wider.

    Args:
        client (Client): Target browser tab.
        max_width (int, optional): Maximum output width in pixels. Defaults to 1280.
        quality (float, optional): JPEG quality, 0.0 to 1.0. Defaults to 0.5.

    Returns:
        dict: {'ok': True, 'image_base64': ..., 'format': 'jpeg', 'width': ..., 'height': ..., 'bytes': ...} or {'ok': False, 'error': ...} (html2canvas_not_loaded, malformed_data_url, js_exception, js_error).
    """

    js = f"""
        (async () => {{
            if (typeof html2canvas === 'undefined') {{
                return {{ok: false, error: 'html2canvas_not_loaded'}};
            }}
            const rendered = await html2canvas(document.body, {{
                backgroundColor: '#ffffff',
                logging: false,
                useCORS: true,
                onclone: (clonedDoc) => {{
                    // See this function's docstring: blob: URL <img>s (e.g.
                    // the pinned-stream dialog's live frame) don't survive
                    // html2canvas's own re-fetch -- swap each one, in the
                    // clone only, for a canvas already painted with that
                    // img's current (already-decoded) bitmap.
                    document.querySelectorAll('img').forEach((liveImg) => {{
                        if (!liveImg.src.startsWith('blob:') || !liveImg.id) return;
                        const clonedImg = clonedDoc.getElementById(liveImg.id);
                        if (!clonedImg || !liveImg.naturalWidth) return;
                        const stand_in = clonedDoc.createElement('canvas');
                        stand_in.width = liveImg.naturalWidth;
                        stand_in.height = liveImg.naturalHeight;
                        stand_in.getContext('2d').drawImage(liveImg, 0, 0);
                        stand_in.className = clonedImg.className;
                        stand_in.style.cssText = clonedImg.style.cssText;
                        clonedImg.replaceWith(stand_in);
                    }});
                }},
            }});
            let out = rendered;
            const maxWidth = {int(max_width)};
            if (rendered.width > maxWidth) {{
                const scale = maxWidth / rendered.width;
                const resized = document.createElement('canvas');
                resized.width = maxWidth;
                resized.height = Math.round(rendered.height * scale);
                resized.getContext('2d').drawImage(rendered, 0, 0, resized.width, resized.height);
                out = resized;
            }}
            return {{
                ok: true,
                data_url: out.toDataURL('image/jpeg', {float(quality)}),
                width: out.width,
                height: out.height,
            }};
        }})()
    """
    try:
        result = await client.run_javascript(js, timeout=15.0)
    except Exception as exc:
        return {'ok': False, 'error': 'js_exception', 'detail': str(exc)}
    if not isinstance(result, dict) or not result.get('ok'):
        return result if isinstance(result, dict) else {'ok': False, 'error': 'js_error'}
    try:
        _, b64 = result['data_url'].split(',', 1)
    except (KeyError, ValueError):
        return {'ok': False, 'error': 'malformed_data_url'}
    return {
        'ok': True,
        'image_base64': b64,
        'format': 'jpeg',
        'width': result.get('width'),
        'height': result.get('height'),
        'bytes': len(base64.b64decode(b64)),
    }


async def _agent_source_frame(source_id: str) -> dict:
    """Return the newest saved frame of a benchmark source.

    Args:
        source_id (str): Id of the source.

    Returns:
        dict: {'ok': True, 'image_base64': ..., 'format': 'jpeg', 'bytes': ...} or {'ok': False, 'error': 'not_found' | 'no_frames_yet'}.
    """

    entry = BENCHMARK_SOURCES.get(source_id)
    if entry is None:
        return {'ok': False, 'error': 'not_found'}
    names = _benchmark_ring_buffer_names(entry['frame_dir'])
    if not names:
        return {'ok': False, 'error': 'no_frames_yet'}
    try:
        data = await asyncio.to_thread(_read_file_bytes, os.path.join(entry['frame_dir'], names[-1]))
    except FileNotFoundError:
        return {'ok': False, 'error': 'no_frames_yet'}
    return {
        'ok': True,
        'image_base64': base64.b64encode(data).decode('ascii'),
        'format': 'jpeg',
        'bytes': len(data),
    }


# Shared secret for the /_agent/* routes; empty disables the check.
GUI_AGENT_API_KEY = os.environ.get('GUI_AGENT_API_KEY', '')


def _require_agent_key(x_agent_key: Optional[str] = Header(default=None)) -> None:
    """Authorize an /_agent/* request (FastAPI dependency).

    Does nothing when GUI_AGENT_API_KEY is empty.

    Args:
        x_agent_key (str, optional): Value of the X-Agent-Key header.

    Raises:
        HTTPException: 401 if a key is configured and the header differs.
    """
    if GUI_AGENT_API_KEY and x_agent_key != GUI_AGENT_API_KEY:
        raise HTTPException(status_code=401, detail='missing or invalid X-Agent-Key header')


def _resolve_agent_client(client_id: str) -> Client:
    """Look up a connected browser tab.

    Args:
        client_id (str): Id of the tab.

    Returns:
        Client: The NiceGUI client.

    Raises:
        HTTPException: 404 if no connected client has that id.
    """
    client = Client.instances.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail=f'no connected client with id {client_id!r}')
    return client


class _AgentClickBody(BaseModel):
    """Request body of POST /_agent/click; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    text: str


class _AgentSetFieldBody(BaseModel):
    """Request body of POST /_agent/set_field; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    label: str
    value: str
    scope_id: Optional[str] = None


class _AgentToggleDropdownBody(BaseModel):
    """Request body of POST /_agent/toggle_dropdown; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    label: str
    scope_id: Optional[str] = None


class _AgentReadDropdownOptionsBody(BaseModel):
    """Request body of POST /_agent/read_dropdown_options; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    label: str
    scope_id: Optional[str] = None


class _AgentTooltipBody(BaseModel):
    """Request body of POST /_agent/tooltip; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    label: str


class _AgentAddNodeBody(BaseModel):
    """Request body of POST /_agent/add_node; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    label: str


class _AgentPositionNodeBody(BaseModel):
    """Request body of POST /_agent/position_node; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    node_id: str
    frac_x: float
    frac_y: float


class _AgentConnectNodesBody(BaseModel):
    """Request body of POST /_agent/connect_nodes; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    source_id: str
    target_id: str


class _AgentOpenNodeBody(BaseModel):
    """Request body of POST /_agent/open_node; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    node_id: str


class _AgentDeleteNodeBody(BaseModel):
    """Request body of POST /_agent/delete_node; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    node_id: str


class _AgentDeleteEdgeBody(BaseModel):
    """Request body of POST /_agent/delete_edge; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    source_id: str
    target_id: str


class _AgentHighlightBody(BaseModel):
    """Request body of POST /_agent/highlight; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    kind: str
    target: Optional[str] = None
    text: Optional[str] = None
    id: Optional[str] = None
    color: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    source_id: Optional[str] = None
    target_id: Optional[str] = None


class _AgentClearHighlightBody(BaseModel):
    """Request body of POST /_agent/clear_highlight; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    id: Optional[str] = None


class _AgentHoverBody(BaseModel):
    """Request body of POST /_agent/hover; the fields mirror the arguments of the matching _agent_* helper."""
    client_id: str
    text: str
    action: str = 'enter'


@app.get('/_agent/sessions')
def _agent_list_sessions_route(_: None = Depends(_require_agent_key)) -> dict:
    """Handle GET /_agent/sessions: list the connected client ids and whether each has a socket connection."""
    return {
        'sessions': [
            {'client_id': cid, 'has_socket_connection': getattr(c, 'has_socket_connection', None)}
            for cid, c in Client.instances.items()
        ],
    }


@app.post('/_agent/click')
async def _agent_click_route(body: _AgentClickBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/click via _agent_click."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_click(client, body.text)


@app.post('/_agent/set_field')
async def _agent_set_field_route(body: _AgentSetFieldBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/set_field via _agent_set_field."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_set_field(client, body.label, body.value, scope_id=body.scope_id)


@app.post('/_agent/toggle_dropdown')
async def _agent_toggle_dropdown_route(body: _AgentToggleDropdownBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/toggle_dropdown via _agent_toggle_dropdown."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_toggle_dropdown(client, body.label, scope_id=body.scope_id)


@app.post('/_agent/read_dropdown_options')
async def _agent_read_dropdown_options_route(body: _AgentReadDropdownOptionsBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/read_dropdown_options via _agent_read_dropdown_options."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_read_dropdown_options(client, body.label, scope_id=body.scope_id)


@app.get('/_agent/state')
async def _agent_get_state_route(client_id: str, _: None = Depends(_require_agent_key)) -> dict:
    """Handle GET /_agent/state via _agent_get_state."""
    client = _resolve_agent_client(client_id)
    return await _agent_get_state(client)


@app.post('/_agent/hover')
async def _agent_hover_route(body: _AgentHoverBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/hover via _agent_hover."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_hover(client, body.text, body.action)


@app.get('/_agent/source_frame')
async def _agent_source_frame_route(source_id: str, _: None = Depends(_require_agent_key)) -> dict:
    """Handle GET /_agent/source_frame via _agent_source_frame."""
    return await _agent_source_frame(source_id)


@app.get('/_agent/screenshot')
async def _agent_screenshot_route(
    client_id: str,
    max_width: int = 1280,
    quality: float = 0.5,
    _: None = Depends(_require_agent_key),
) -> dict:
    """Handle GET /_agent/screenshot via _agent_screenshot."""
    client = _resolve_agent_client(client_id)
    return await _agent_screenshot(client, max_width, quality)


@app.get('/_agent/notifications')
def _agent_get_notifications_route(client_id: str, since_id: int = 0,
                                    _: None = Depends(_require_agent_key)) -> dict:
    """Handle GET /_agent/notifications: return {'notifications': [...]} newer than since_id."""
    _resolve_agent_client(client_id)
    return {'notifications': _agent_get_notifications(client_id, since_id=since_id)}


@app.post('/_agent/tooltip')
async def _agent_tooltip_route(body: _AgentTooltipBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/tooltip via _agent_get_tooltip."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_get_tooltip(client, body.label)


@app.get('/_agent/get_text')
async def _agent_get_text_route(client_id: str, contains: str, _: None = Depends(_require_agent_key)) -> dict:
    """Handle GET /_agent/get_text via _agent_get_text."""
    client = _resolve_agent_client(client_id)
    return await _agent_get_text(client, contains)


@app.get('/_agent/graph')
def _agent_get_graph_route(client_id: str, _: None = Depends(_require_agent_key)) -> dict:
    """Handle GET /_agent/graph via _agent_get_graph."""
    client = _resolve_agent_client(client_id)
    return _agent_get_graph(client)


@app.post('/_agent/add_node')
async def _agent_add_node_route(body: _AgentAddNodeBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/add_node via _agent_add_node."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_add_node(client, body.label)


@app.post('/_agent/position_node')
async def _agent_position_node_route(body: _AgentPositionNodeBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/position_node via _agent_position_node."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_position_node(client, body.node_id, body.frac_x, body.frac_y)


@app.post('/_agent/connect_nodes')
async def _agent_connect_nodes_route(body: _AgentConnectNodesBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/connect_nodes via _agent_connect_nodes."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_connect_nodes(client, body.source_id, body.target_id)


@app.post('/_agent/open_node')
async def _agent_open_node_route(body: _AgentOpenNodeBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/open_node via _agent_open_node."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_open_node(client, body.node_id)


@app.post('/_agent/delete_node')
async def _agent_delete_node_route(body: _AgentDeleteNodeBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/delete_node via _agent_delete_node."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_delete_node(client, body.node_id)


@app.post('/_agent/delete_edge')
async def _agent_delete_edge_route(body: _AgentDeleteEdgeBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/delete_edge via _agent_delete_edge."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_delete_edge(client, body.source_id, body.target_id)


@app.post('/_agent/highlight')
async def _agent_highlight_route(body: _AgentHighlightBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/highlight via _agent_highlight."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_highlight(
        client, body.kind, body.target, body.text,
        id=body.id, color=body.color, x=body.x, y=body.y,
        source_id=body.source_id, target_id=body.target_id,
    )


@app.post('/_agent/clear_highlight')
async def _agent_clear_highlight_route(body: _AgentClearHighlightBody, _: None = Depends(_require_agent_key)) -> dict:
    """Handle POST /_agent/clear_highlight via _agent_clear_highlight."""
    client = _resolve_agent_client(body.client_id)
    return await _agent_clear_highlight(client, body.id)

