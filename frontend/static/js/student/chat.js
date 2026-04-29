/**
 * Student AI tutor chat page.
 *
 * Hydrates from `/api/v1/tutoring/sessions/<id>/` for the active session,
 * sends new messages to `/api/v1/tutoring/sessions/<id>/messages/`, and
 * renders citations as clickable chips that surface the source chunks
 * already returned by the API. No markdown rendering yet — content is
 * shown as preserved-whitespace text plus inline citation chips.
 */

(function () {
    'use strict';

    const API_ROOT = '/api/v1/tutoring/sessions/';

    // ------------------------------ DOM refs

    const shell = document.querySelector('.chat-shell');
    if (!shell) return;

    const sessionId = shell.dataset.sessionId || null;

    const messagesBody = document.getElementById('messages-body');
    const composer = document.getElementById('composer');
    const composerInput = document.getElementById('composer-input');
    const composerSend = document.getElementById('composer-send');

    const newSessionBtn = document.getElementById('btn-new-session');
    const emptyNewBtn = document.getElementById('btn-empty-new-session');
    const newSessionModal = document.getElementById('new-session-modal');
    const newSessionForm = document.getElementById('new-session-form');
    const newSessionCancel = document.getElementById('new-session-cancel');
    const newSessionSubject = document.getElementById('new-session-subject');

    // ------------------------------ helpers

    function escapeHtml(str) {
        return (str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatContent(text) {
        // Render plain text with whitespace preserved, then upgrade [N]
        // tokens into clickable citation chips.
        const safe = escapeHtml(text);
        return safe.replace(/\[(\d+)\]/g, (_, n) => (
            `<span class="chat-citation" data-citation="${n}">[${n}]</span>`
        ));
    }

    function renderSources(sources) {
        if (!sources || !sources.length) return '';
        const rows = sources.map((src, i) => {
            const idx = i + 1;
            const page = src.page_number ? ` (p. ${src.page_number})` : '';
            const path = src.node_id ? `<span class="chat-source-row__path">· ${escapeHtml(src.node_id)}</span>` : '';
            const snippet = src.snippet ? `<div class="chat-source-row__snippet">${escapeHtml(src.snippet)}</div>` : '';
            return `
                <div class="chat-source-row" data-source="${idx}">
                    <span class="chat-source-row__index">[${idx}]</span>
                    <span class="chat-source-row__title">${escapeHtml(src.title || src.document_title || 'Source')}${page}</span>
                    ${path}
                    ${snippet}
                </div>
            `;
        }).join('');
        return `
            <div class="chat-sources">
                <h4 class="chat-sources__title">Sources</h4>
                ${rows}
            </div>
        `;
    }

    function renderMessage(msg) {
        const isStudent = msg.role === 'student';
        const cls = isStudent ? 'chat-message--student' : 'chat-message--assistant';

        const sources = !isStudent ? renderSources(msg.retrieved_chunks || []) : '';
        const stubBadge = !isStudent && msg.model === 'stub'
            ? '<span class="chat-bubble__model-badge" title="Running without an LLM API key">offline</span>'
            : '';
        const meta = isStudent
            ? ''
            : `<span class="chat-bubble__meta">Tutor${stubBadge}</span>`;

        return `
            <div class="chat-message ${cls}" data-message-id="${msg.id || ''}">
                <div class="chat-bubble">
                    <div class="chat-bubble__content">${formatContent(msg.content)}</div>
                    ${meta}
                    ${sources}
                </div>
            </div>
        `;
    }

    function appendMessage(msg) {
        if (!messagesBody) return;
        messagesBody.insertAdjacentHTML('beforeend', renderMessage(msg));
        messagesBody.scrollTop = messagesBody.scrollHeight;
        wireCitationClicks();
    }

    function wireCitationClicks() {
        // Clicking [N] in an answer expands the matching source row.
        document.querySelectorAll('.chat-citation').forEach(el => {
            if (el.dataset.bound === '1') return;
            el.dataset.bound = '1';
            el.addEventListener('click', () => {
                const idx = el.dataset.citation;
                const bubble = el.closest('.chat-bubble');
                if (!bubble) return;
                const row = bubble.querySelector(`.chat-source-row[data-source="${idx}"]`);
                if (!row) return;
                document.querySelectorAll('.chat-source-row.is-open').forEach(r => {
                    if (r !== row) r.classList.remove('is-open');
                });
                row.classList.toggle('is-open');
                row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            });
        });
        document.querySelectorAll('.chat-source-row').forEach(row => {
            if (row.dataset.bound === '1') return;
            row.dataset.bound = '1';
            row.addEventListener('click', e => {
                if (e.target.closest('.chat-source-row__snippet')) return;
                row.classList.toggle('is-open');
            });
        });
    }

    // ------------------------------ load history

    async function loadSessionHistory() {
        if (!sessionId || !messagesBody) return;
        const result = await APIClient.get(`${API_ROOT}${sessionId}/`, null, { showSuccessToast: false });
        if (!result.success) {
            messagesBody.innerHTML = `<div class="chat-error">Could not load this conversation.</div>`;
            return;
        }
        const messages = (result.data && result.data.messages) || [];
        if (messages.length === 0) {
            messagesBody.innerHTML = `<div class="chat-loading">Ask your first question to get started.</div>`;
            return;
        }
        messagesBody.innerHTML = messages.map(renderMessage).join('');
        messagesBody.scrollTop = messagesBody.scrollHeight;
        wireCitationClicks();
    }

    // ------------------------------ send

    async function sendMessage(content) {
        if (!sessionId) return;

        composerSend.disabled = true;
        composerSend.textContent = 'Thinking…';

        // Optimistic user bubble
        const optimistic = {
            id: `tmp-${Date.now()}`,
            role: 'student',
            content,
            retrieved_chunks: [],
            model: '',
        };
        // Drop the placeholder text if it's still there
        const placeholder = messagesBody.querySelector('.chat-loading');
        if (placeholder) placeholder.remove();
        appendMessage(optimistic);

        const result = await APIClient.post(
            `${API_ROOT}${sessionId}/messages/`,
            { content },
            { showSuccessToast: false }
        );

        composerSend.disabled = false;
        composerSend.textContent = 'Send';
        composerInput.focus();

        if (!result.success) {
            // Hide our optimistic bubble (re-load to keep state consistent)
            await loadSessionHistory();
            return;
        }

        const data = result.data || {};
        // Replace optimistic with real persisted user_message
        const tmpEl = messagesBody.querySelector(`[data-message-id="${optimistic.id}"]`);
        if (tmpEl && data.user_message) {
            tmpEl.outerHTML = renderMessage(data.user_message);
        }
        if (data.assistant_message) {
            appendMessage(data.assistant_message);
        }
    }

    if (composer) {
        composer.addEventListener('submit', (e) => {
            e.preventDefault();
            const text = (composerInput.value || '').trim();
            if (!text) return;
            composerInput.value = '';
            sendMessage(text);
        });
    }

    if (composerInput) {
        composerInput.addEventListener('keydown', (e) => {
            // Cmd/Ctrl+Enter submits
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                composer.requestSubmit();
            }
        });
    }

    // ------------------------------ new session modal

    function openModal() {
        if (newSessionModal && typeof newSessionModal.showModal === 'function') {
            newSessionModal.showModal();
        }
    }

    function closeModal() {
        if (newSessionModal && typeof newSessionModal.close === 'function') {
            newSessionModal.close();
        }
    }

    if (newSessionBtn) newSessionBtn.addEventListener('click', openModal);
    if (emptyNewBtn) emptyNewBtn.addEventListener('click', openModal);
    if (newSessionCancel) newSessionCancel.addEventListener('click', () => closeModal());

    if (newSessionForm) {
        newSessionForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const subjectVal = newSessionSubject ? newSessionSubject.value : '';
            const payload = {};
            if (subjectVal) payload.subject = parseInt(subjectVal, 10);

            const result = await APIClient.post(API_ROOT, payload, { showSuccessToast: false });
            if (result.success && result.data && result.data.id) {
                closeModal();
                window.location.href = `/student/chat/${result.data.id}/`;
            }
        });
    }

    // ------------------------------ boot

    if (sessionId) {
        loadSessionHistory();
        if (composerInput) composerInput.focus();
    }
})();
