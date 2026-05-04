/* =========================================================================
   Codex rail — loads curriculum node detail when a citation chip is clicked.
   Runs alongside chat.js; it doesn't touch any of chat.js's state or DOM.

   Trigger contract:
     Any element (created by chat.js or the template) that has a non-empty
     `data-node-id` attribute opens the Codex when clicked. In practice this
     is the `.chat-citation` chip and the `.chat-source-row` row; both are
     stamped with `data-node-id` by chat.js using the CharField
     `ContentNode.node_id` carried through `RetrievedChunk`.

   API:
     GET /api/v1/curriculum/nodes/<pk_or_node_id>/
     The endpoint accepts either the integer PK or the CharField node_id
     (see apps/service/api/curriculum.py), so citations can pass the
     `node_id` string directly with no client-side lookup.
   ========================================================================= */

(function () {
    'use strict';

    const rail = document.getElementById('codex-rail');
    const body = document.getElementById('codex-body');
    const closeBtn = document.getElementById('codex-close');
    if (!rail || !body) return;

    // ------------------------------------------------------------------- helpers

    function escapeHtml(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function emptyState() {
        body.innerHTML =
            '<div class="codex-empty">' +
                '<p class="sys-text-muted sys-mono" style="font-size:0.75rem; letter-spacing:0.1em; margin:0;">' +
                    'No topic selected' +
                '</p>' +
            '</div>';
        if (closeBtn) closeBtn.style.display = 'none';
    }

    function loadingState() {
        body.innerHTML =
            '<div class="codex-empty sys-mono sys-text-dim">Loading topic…</div>';
        if (closeBtn) closeBtn.style.display = 'inline-flex';
    }

    function errorState(msg) {
        body.innerHTML =
            '<div class="codex-empty sys-mono sys-text-crimson">' +
            escapeHtml(msg || 'Could not load topic.') +
            '</div>';
        if (closeBtn) closeBtn.style.display = 'inline-flex';
    }

    // Render the node payload returned by /api/v1/curriculum/nodes/<id>/.
    function renderNode(node) {
        const breadcrumb = (node.breadcrumb || [])
            .map(b => '<span>' + escapeHtml(b.title) + '</span>')
            .join(' <span class="codex-bc-sep">→</span> ');

        const related = (node.related || [])
            .map(r =>
                '<li>' +
                '<a href="#" class="codex-related-link" data-node-id="' +
                escapeHtml(r.node_id || r.id) + '">' +
                escapeHtml(r.title) +
                '</a>' +
                '</li>',
            )
            .join('');

        // Render Markdown if marked + DOMPurify are present (chat.html loads
        // them), fall back to a plain-text-with-<br> rendering otherwise.
        let contentHtml = '';
        const raw = node.content == null ? '' : String(node.content);
        if (typeof window.marked !== 'undefined') {
            const parsed = window.marked.parse(raw);
            contentHtml = window.DOMPurify
                ? window.DOMPurify.sanitize(parsed)
                : parsed;
        } else {
            contentHtml = escapeHtml(raw).replace(/\n/g, '<br>');
        }

        const pageLabel = node.page_number
            ? '<span class="codex-page sys-mono sys-text-dim">p. ' +
              escapeHtml(node.page_number) + '</span>'
            : '';

        const subjectChip = (node.subject && node.subject.name)
            ? '<span class="sys-chip sys-chip--cyan">' +
              escapeHtml(node.subject.name) + '</span>'
            : '';

        body.innerHTML =
            '<div class="codex-node sys-anim-reveal">' +
                (breadcrumb
                    ? '<nav class="codex-breadcrumb sys-mono">' + breadcrumb + '</nav>'
                    : '') +
                '<div class="codex-node-head">' +
                    subjectChip +
                    pageLabel +
                '</div>' +
                '<h2 class="codex-node-title">' + escapeHtml(node.title) + '</h2>' +
                '<div class="codex-node-body">' + contentHtml + '</div>' +
                (related
                    ? '<h4 class="codex-related-heading sys-panel-title">RELATED</h4>' +
                      '<ul class="codex-related-list">' + related + '</ul>'
                    : '') +
            '</div>';

        // Math typesetting if KaTeX auto-render is present on the page.
        if (typeof window.renderMathInElement === 'function') {
            try {
                window.renderMathInElement(body, {
                    delimiters: [
                        { left: '$$', right: '$$', display: true },
                        { left: '\\[', right: '\\]', display: true },
                        { left: '$',  right: '$',  display: false },
                        { left: '\\(', right: '\\)', display: false },
                    ],
                    throwOnError: false,
                    ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
                });
            } catch (_) { /* non-fatal */ }
        }

        if (closeBtn) closeBtn.style.display = 'inline-flex';
    }

    // ------------------------------------------------------------------- fetch

    async function loadNode(nodeId) {
        if (!nodeId) return;
        loadingState();
        try {
            const resp = await fetch(
                '/api/v1/curriculum/nodes/' + encodeURIComponent(nodeId) + '/',
                {
                    headers: { 'Accept': 'application/json' },
                    credentials: 'same-origin',
                },
            );
            if (!resp.ok) {
                if (resp.status === 404) {
                    errorState('Topic not found.');
                } else {
                    errorState('Could not load topic (HTTP ' + resp.status + ').');
                }
                return;
            }
            const data = await resp.json();
            renderNode(data);
        } catch (err) {
            errorState('Could not load topic.');
        }
    }

    // ------------------------------------------------------------------- wiring

    // Delegate clicks on anything with a data-node-id attribute. This covers
    // the `.chat-citation` chips created by chat.js (which carry the source
    // chunk's node_id) as well as `.chat-source-row` rows and Codex-internal
    // "Related" links. Empty node_id values are ignored.
    document.addEventListener('click', (ev) => {
        const trigger = ev.target.closest('[data-node-id]');
        if (!trigger) return;
        const id = (trigger.getAttribute('data-node-id') || '').trim();
        if (!id) return;
        ev.preventDefault();
        loadNode(id);
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', emptyState);
    }
})();
