/**
 * Overlay that draws highlight boxes, labels and pointer arrows over the GUI, used by the agent
 * surface (`agent_surface.py`) to point at widgets in screenshots.
 *
 * Entry points: `window.__annotateHighlight(spec)`, `window.__annotateClear(id)` and
 * `window.__annotateClearAll()`. Elements are drawn into a `#gui-annotate-root` container and styled by
 * `annotate_overlay.css`. Targets are looked up inside the topmost visible dialog, or the whole document
 * when no dialog is open.
 *
 * `window.__guiAnnotations` maps annotation id to the DOM elements created for it.
 */
window.__guiAnnotations = window.__guiAnnotations || {};

/** Return the overlay container element, creating it under `body` on first use. */
function __annotateRoot() {
    let root = document.getElementById('gui-annotate-root');
    if (!root) {
        root = document.createElement('div');
        root.id = 'gui-annotate-root';
        document.body.appendChild(root);
    }
    return root;
}

/** Return true if the element takes up layout space (non-zero size or client rects). */
function __annotateIsVisible(el) {
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
}

/** Return the topmost visible `.q-dialog`, or `document` when none is open. Lookups are scoped to it. */
function __annotateScopeRoot() {
    const dialogs = [...document.querySelectorAll('.q-dialog')].filter(__annotateIsVisible);
    return dialogs.length ? dialogs[dialogs.length - 1] : document;
}

/**
 * Find a button, tab, checkbox or toggle by its label.
 * Each candidate is matched on its text, the text of its row (checkbox/toggle without own text), its icon
 * name and its aria-label, case-insensitively: an exact match scores 2, a substring match 1.
 *
 * Args: target: label text to look for.
 * Returns: `{ok: true, el, kind}`, or `{ok: false, error: 'not_found'}`, or
 *     `{ok: false, error: 'ambiguous', matched_count}` when several candidates tie for the best score.
 */
function __annotateResolveWidget(target) {
    const norm = s => (s || '').trim().toLowerCase();
    const wanted = norm(target);
    const labelsFor = el => {
        const icon = el.querySelector('i.material-icons, i.q-icon');
        const own = el.textContent.trim();
        let rowText = '';
        if (!own && (el.classList.contains('q-checkbox') || el.classList.contains('q-toggle'))) {
            const row = el.parentElement ? el.parentElement.closest('.row') : null;
            if (row) rowText = row.textContent.trim();
        }
        return [own, rowText, icon ? icon.textContent.trim() : '', (el.getAttribute('aria-label') || '').trim()].filter(Boolean);
    };
    const root = __annotateScopeRoot();
    const seen = new Set();
    const candidates = [];
    const add = (el, kind) => { if (!seen.has(el)) { seen.add(el); candidates.push({el, kind}); } };
    root.querySelectorAll('button, .q-btn').forEach(el => { if (__annotateIsVisible(el)) add(el, 'button'); });
    root.querySelectorAll('.q-tab').forEach(el => { if (__annotateIsVisible(el)) add(el, 'tab'); });
    root.querySelectorAll('.q-checkbox, .q-toggle').forEach(el => { if (__annotateIsVisible(el)) add(el, 'toggle'); });
    const scored = candidates.map(c => {
        const labels = labelsFor(c.el).map(norm);
        let score = 0;
        if (labels.some(l => l === wanted)) score = 2;
        else if (labels.some(l => l.includes(wanted))) score = 1;
        return {el: c.el, kind: c.kind, score};
    }).filter(c => c.score > 0);
    if (scored.length === 0) return {ok: false, error: 'not_found'};
    const best = Math.max(...scored.map(c => c.score));
    const top = scored.filter(c => c.score === best);
    if (top.length > 1) return {ok: false, error: 'ambiguous', matched_count: top.length};
    return {ok: true, el: top[0].el, kind: top[0].kind};
}

/**
 * Find a Quasar input field whose label contains the target text (case-insensitive).
 * Returns the same result shape as `__annotateResolveWidget`; `el` is the field's control box, `kind` is 'field'.
 */
function __annotateResolveField(target) {
    const norm = s => (s || '').trim().toLowerCase();
    const wanted = norm(target);
    const root = __annotateScopeRoot();
    const fields = [...root.querySelectorAll('.q-field')].filter(__annotateIsVisible);
    const matches = fields.filter(f => {
        const lab = f.querySelector('.q-field__label');
        return lab && norm(lab.textContent).includes(wanted);
    });
    if (matches.length === 0) return {ok: false, error: 'not_found'};
    if (matches.length > 1) return {ok: false, error: 'ambiguous', matched_count: matches.length};
    const control = matches[0].querySelector('.q-field__control') || matches[0];
    return {ok: true, el: control, kind: 'field'};
}

/** Find a Vue Flow node by `data-id`. Returns `{ok, el, kind: 'node'}` or `{ok: false, error: 'not_found'}`. */
function __annotateResolveNode(nodeId) {
    const root = __annotateScopeRoot();
    const el = root.querySelector('.vue-flow__node[data-id="' + CSS.escape(nodeId || '') + '"]');
    if (!el) return {ok: false, error: 'not_found'};
    return {ok: true, el, kind: 'node'};
}

/** Find a Vue Flow edge by `data-id`. Returns `{ok, el, kind: 'edge'}` or `{ok: false, error: 'not_found'}`. */
function __annotateResolveEdge(edgeId) {
    const root = __annotateScopeRoot();
    const el = root.querySelector('.vue-flow__edge[data-id="' + CSS.escape(edgeId || '') + '"]');
    if (!el) return {ok: false, error: 'not_found'};
    return {ok: true, el, kind: 'edge'};
}

/** Find the card of the topmost visible dialog. Returns `{ok, el, kind: 'dialog'}` or a not_found error. */
function __annotateResolveDialog() {
    const dialogs = [...document.querySelectorAll('.q-dialog')].filter(__annotateIsVisible);
    if (dialogs.length === 0) return {ok: false, error: 'not_found'};
    const card = dialogs[dialogs.length - 1].querySelector('.q-card') || dialogs[dialogs.length - 1];
    return {ok: true, el: card, kind: 'dialog'};
}

/**
 * Find the single visible leaf element whose text contains the target (case-insensitive).
 * Returns `{ok, el, kind: 'text'}`, or a not_found / ambiguous error.
 */
function __annotateResolveText(target) {
    const norm = s => (s || '').trim().toLowerCase();
    const wanted = norm(target);
    const root = __annotateScopeRoot();
    const all = [...root.querySelectorAll('*')]
        .filter(el => el.children.length === 0 && __annotateIsVisible(el) && norm(el.textContent).includes(wanted));
    if (all.length === 0) return {ok: false, error: 'not_found'};
    if (all.length > 1) return {ok: false, error: 'ambiguous', matched_count: all.length};
    return {ok: true, el: all[0], kind: 'text'};
}

/**
 * Find a node-palette tree entry whose text equals the target exactly (case-sensitive).
 * Returns `{ok, el, kind: 'palette'}` with the tree node header as `el`, or a not_found / ambiguous error.
 */
function __annotateResolvePaletteLeaf(target) {
    const wanted = (target || '').trim();
    const root = __annotateScopeRoot();
    const divs = [...root.querySelectorAll('.q-tree__node-header-content > div')]
        .filter(el => __annotateIsVisible(el) && el.textContent.trim() === wanted);
    if (divs.length === 0) return {ok: false, error: 'not_found'};
    if (divs.length > 1) return {ok: false, error: 'ambiguous', matched_count: divs.length};
    const header = divs[0].closest('.q-tree__node-header') || divs[0];
    return {ok: true, el: header, kind: 'palette'};
}

// Per-kind padding (px) between the target and its highlight box.
const __ANNOTATE_PAD = {button: 6, tab: 6, toggle: 4, field: 4, node: 6, edge: 4, dialog: 8, text: 3, palette: 4};
// Per-kind corner radius (px) of the highlight box.
const __ANNOTATE_RADIUS = {button: 8, tab: 8, toggle: 20, field: 4, node: 10, edge: 4, dialog: 12, text: 3, palette: 6};

/**
 * Append a label to the overlay and position it centred below the anchor rectangle, or above it when it
 * would not fit, keeping 8 px from the viewport edges.
 *
 * Args:
 *     root: overlay container.
 *     labelEl: label element to place.
 *     anchorRect: `{left, top, bottom, width}` of the highlighted box.
 */
function __annotatePlaceLabel(root, labelEl, anchorRect) {
    root.appendChild(labelEl);
    const vw = window.innerWidth, vh = window.innerHeight;
    const lw = labelEl.offsetWidth, lh = labelEl.offsetHeight;
    let top = anchorRect.bottom + 10;
    if (top + lh > vh - 8) top = anchorRect.top - lh - 10;
    top = Math.max(8, top);
    let left = anchorRect.left + anchorRect.width / 2 - lw / 2;
    left = Math.max(8, Math.min(left, vw - lw - 8));
    labelEl.style.top = top + 'px';
    labelEl.style.left = left + 'px';
}

/** Remove the annotation with the given id, if present. */
window.__annotateClear = function(id) {
    const existing = window.__guiAnnotations[id];
    if (existing) {
        existing.forEach(el => el.remove());
        delete window.__guiAnnotations[id];
    }
};

/** Remove every annotation and empty the overlay container. */
window.__annotateClearAll = function() {
    const root = document.getElementById('gui-annotate-root');
    if (root) root.innerHTML = '';
    window.__guiAnnotations = {};
};

/**
 * Draw an annotation for a target, replacing any earlier annotation with the same id.
 *
 * Args:
 *     spec: object with
 *         id: annotation id (random when omitted).
 *         kind: 'auto' (default), 'button', 'tab', 'toggle', 'field', 'text', 'node', 'edge', 'dialog',
 *             'palette' or 'pointer'. 'auto' tries widget, then field, then text.
 *         target: label text, or node/edge id for those kinds.
 *         text: optional caption drawn next to the annotation.
 *         color: CSS color, default '#ff5252'.
 *         x, y: viewport fractions (0..1) for a pointer when no element is resolved.
 *
 * Returns:
 *     `{ok: true, id, kind, rect}` for a highlight box, `{ok: true, id, kind: 'pointer', point}` for a
 *     dot with a caption arrow, or `{ok: false, error, matched_count?}`. When the element lookup fails,
 *     a pointer is drawn if `x`/`y` are given or the target text is found; kind 'pointer' without a
 *     usable position returns error 'no_target'.
 */
window.__annotateHighlight = function(spec) {
    const id = spec.id || ('anno-' + Math.random().toString(36).slice(2));
    const kind = spec.kind || 'auto';
    const color = spec.color || '#ff5252';
    window.__annotateClear(id);

    let resolved;
    if (kind === 'dialog') {
        resolved = __annotateResolveDialog();
    } else if (kind === 'node') {
        resolved = __annotateResolveNode(spec.target);
    } else if (kind === 'edge') {
        resolved = __annotateResolveEdge(spec.target);
    } else if (kind === 'button' || kind === 'tab' || kind === 'toggle') {
        resolved = __annotateResolveWidget(spec.target);
    } else if (kind === 'field') {
        resolved = __annotateResolveField(spec.target);
    } else if (kind === 'text') {
        resolved = __annotateResolveText(spec.target);
    } else if (kind === 'palette') {
        resolved = __annotateResolvePaletteLeaf(spec.target);
    } else if (kind === 'auto') {
        resolved = __annotateResolveWidget(spec.target);
        if (!resolved.ok) resolved = __annotateResolveField(spec.target);
        if (!resolved.ok) resolved = __annotateResolveText(spec.target);
    } else if (kind === 'pointer') {
        resolved = {ok: false, error: 'pointer_requested'};
    } else {
        return {ok: false, error: 'unknown_kind', kind};
    }

    const root = __annotateRoot();

    if (resolved.ok) {
        resolved.el.scrollIntoView({block: 'nearest', inline: 'nearest'});
        const rect = resolved.el.getBoundingClientRect();
        const pad = __ANNOTATE_PAD[resolved.kind] ?? 6;
        const radius = __ANNOTATE_RADIUS[resolved.kind] ?? 6;
        const box = document.createElement('div');
        box.className = 'gui-annotate-highlight gui-annotate-highlight--' + resolved.kind;
        box.style.setProperty('--gac', color);
        box.style.left = (rect.x - pad) + 'px';
        box.style.top = (rect.y - pad) + 'px';
        box.style.width = (rect.width + pad * 2) + 'px';
        box.style.height = (rect.height + pad * 2) + 'px';
        box.style.borderRadius = radius + 'px';
        root.appendChild(box);
        const created = [box];
        if (spec.text) {
            const label = document.createElement('div');
            label.className = 'gui-annotate-label';
            label.style.setProperty('--gac', color);
            label.textContent = spec.text;
            __annotatePlaceLabel(root, label, {
                left: rect.x - pad, top: rect.y - pad,
                bottom: rect.y + rect.height + pad, width: rect.width + pad * 2,
            });
            created.push(label);
        }
        window.__guiAnnotations[id] = created;
        return {ok: true, id, kind: resolved.kind, rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}};
    }

    let point = null;
    if (typeof spec.x === 'number' && typeof spec.y === 'number') {
        point = {x: spec.x * window.innerWidth, y: spec.y * window.innerHeight};
    } else if (spec.target) {
        const textHit = __annotateResolveText(spec.target);
        if (textHit.ok) {
            textHit.el.scrollIntoView({block: 'nearest', inline: 'nearest'});
            const r = textHit.el.getBoundingClientRect();
            point = {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }
    }
    if (!point) {
        return {ok: false, error: resolved.error === 'pointer_requested' ? 'no_target' : resolved.error,
                 matched_count: resolved.matched_count || 0};
    }

    const vw = window.innerWidth, vh = window.innerHeight;
    const dot = document.createElement('div');
    dot.className = 'gui-annotate-pointer-dot';
    dot.style.setProperty('--gac', color);
    dot.style.left = (point.x - 7) + 'px';
    dot.style.top = (point.y - 7) + 'px';
    root.appendChild(dot);
    const created = [dot];

    if (spec.text) {
        const label = document.createElement('div');
        label.className = 'gui-annotate-label';
        label.style.setProperty('--gac', color);
        label.textContent = spec.text;
        root.appendChild(label);
        let bx = point.x + 40, by = point.y - 60;
        const lw = label.offsetWidth, lh = label.offsetHeight;
        if (bx + lw > vw - 8) bx = point.x - lw - 40;
        if (by < 8) by = point.y + 40;
        if (by + lh > vh - 8) by = vh - lh - 8;
        bx = Math.max(8, bx);
        label.style.left = bx + 'px';
        label.style.top = by + 'px';
        created.push(label);

        const labelRect = label.getBoundingClientRect();
        const anchorX = Math.max(labelRect.left, Math.min(point.x, labelRect.right));
        const anchorY = Math.max(labelRect.top, Math.min(point.y, labelRect.bottom));
        const svgNS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(svgNS, 'svg');
        svg.setAttribute('class', 'gui-annotate-arrow-svg');
        svg.setAttribute('width', String(vw));
        svg.setAttribute('height', String(vh));
        const markerId = 'gui-annotate-arrowhead-' + id.replace(/[^a-zA-Z0-9_-]/g, '');
        const defsMarker = document.createElementNS(svgNS, 'defs');
        defsMarker.innerHTML = '<marker id="' + markerId + '" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">' +
            '<path d="M0,0 L8,4 L0,8 Z" fill="' + color + '"/></marker>';
        svg.appendChild(defsMarker);
        const line = document.createElementNS(svgNS, 'line');
        line.setAttribute('x1', String(anchorX));
        line.setAttribute('y1', String(anchorY));
        line.setAttribute('x2', String(point.x));
        line.setAttribute('y2', String(point.y));
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-width', '3');
        line.setAttribute('marker-end', 'url(#' + markerId + ')');
        svg.appendChild(line);
        root.appendChild(svg);
        created.push(svg);
    }

    window.__guiAnnotations[id] = created;
    return {ok: true, id, kind: 'pointer', point};
};
