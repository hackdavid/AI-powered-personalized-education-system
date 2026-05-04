/* =========================================================================
   Quest Chamber — one-question-at-a-time take view.
   Autosaves to /quests/<id>/save-draft/ every 5 seconds + on question change.
   Submits to /quests/<id>/submit/ and redirects to /quests/<id>/results/.
   ========================================================================= */

(function () {
    'use strict';

    const payload = Array.isArray(window.__QUEST_PAYLOAD__)
        ? window.__QUEST_PAYLOAD__
        : [];
    const SAVE_URL = window.__QUEST_SAVE_URL__ || '';
    const SUBMIT_URL = window.__QUEST_SUBMIT_URL__ || '';
    const RESULTS_URL = window.__QUEST_RESULTS_URL__ || '';
    const LIST_URL = window.__QUEST_LIST_URL__ || '/student/quests/';

    const state = {
        index: 0,
        dirty: false,
        answers: payload.map(q => ({
            question_id: q.id,
            selected_option_key: q.saved_selection || '',
            answer_text: q.saved_text || '',
        })),
    };

    const elProgress = document.getElementById('chamber-progress');
    const elQNumber = document.getElementById('chamber-q-number');
    const elQMarks = document.getElementById('chamber-q-marks');
    const elQText = document.getElementById('chamber-q-text');
    const elQInteract = document.getElementById('chamber-q-interact');
    const elPrev = document.getElementById('chamber-prev');
    const elNext = document.getElementById('chamber-next');
    const elSubmit = document.getElementById('chamber-submit');
    const elExit = document.getElementById('chamber-exit');
    const elSaveStatus = document.getElementById('chamber-save-status');

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function setSaveStatus(label, variant) {
        if (!elSaveStatus) return;
        elSaveStatus.textContent = label;
        elSaveStatus.className = 'chamber-save-status';
        if (variant) elSaveStatus.classList.add('chamber-save-status--' + variant);
    }

    function renderProgress() {
        if (!elProgress) return;
        elProgress.innerHTML = '';
        state.answers.forEach((a, i) => {
            const dot = document.createElement('span');
            dot.className = 'chamber-dot';
            if (i === state.index) dot.classList.add('chamber-dot--current');
            if ((a.selected_option_key || a.answer_text) && i !== state.index) {
                dot.classList.add('chamber-dot--answered');
            } else if ((a.selected_option_key || a.answer_text) && i === state.index) {
                // current-and-answered: just show current
            }
            dot.setAttribute('title', 'Question ' + (i + 1));
            elProgress.appendChild(dot);
        });
    }

    function renderQuestion() {
        if (!payload.length) {
            elQText.textContent = 'This quest has no questions.';
            elSubmit.disabled = true;
            return;
        }
        const q = payload[state.index];
        const answer = state.answers[state.index];
        elQNumber.textContent = 'Q ' + (state.index + 1) + ' / ' + payload.length;
        elQMarks.textContent = q.marks + (q.marks === 1 ? ' mark' : ' marks');
        elQText.textContent = q.text;
        elQInteract.innerHTML = '';

        if (q.type === 'mcq') {
            const list = document.createElement('div');
            list.className = 'chamber-options';
            (q.options || []).forEach(opt => {
                const key = (opt && opt.key) || '';
                const text = (opt && opt.text) || '';
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'chamber-option';
                if (answer.selected_option_key === key) {
                    row.classList.add('chamber-option--selected');
                }
                row.innerHTML =
                    '<span class="chamber-option-key">' + escapeHtml(key) + '</span>' +
                    '<span class="chamber-option-text"></span>';
                row.querySelector('.chamber-option-text').textContent = text;
                row.addEventListener('click', () => {
                    answer.selected_option_key = key;
                    answer.answer_text = '';
                    state.dirty = true;
                    renderQuestion();
                    renderProgress();
                    scheduleSave(true);
                });
                list.appendChild(row);
            });
            elQInteract.appendChild(list);
        } else {
            const ta = document.createElement('textarea');
            ta.className = 'chamber-textarea';
            ta.placeholder = q.type === 'essay'
                ? 'Write your answer…'
                : 'Short answer…';
            ta.value = answer.answer_text || '';
            ta.addEventListener('input', () => {
                answer.answer_text = ta.value;
                state.dirty = true;
                renderProgress();
            });
            ta.addEventListener('blur', () => scheduleSave(true));
            elQInteract.appendChild(ta);
        }

        elPrev.disabled = state.index === 0;
        elNext.disabled = state.index === payload.length - 1;
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    let saveTimer = null;
    function scheduleSave(immediate) {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(persist, immediate ? 400 : 5000);
    }

    async function persist() {
        if (!state.dirty || !SAVE_URL) return;
        setSaveStatus('Saving…', 'saving');
        try {
            const resp = await fetch(SAVE_URL, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify({ answers: state.answers }),
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            state.dirty = false;
            setSaveStatus('Saved', 'saved');
            setTimeout(() => setSaveStatus('', ''), 2000);
        } catch (err) {
            setSaveStatus('Save failed — retrying', 'error');
            setTimeout(scheduleSave, 5000);
        }
    }

    async function submit() {
        if (!SUBMIT_URL) return;
        const unanswered = state.answers.filter(a =>
            !a.selected_option_key && !a.answer_text).length;
        const msg = unanswered
            ? `You have ${unanswered} unanswered question(s). Submit anyway?`
            : 'Submit your quest? This cannot be undone.';
        if (!window.confirm(msg)) return;
        setSaveStatus('Submitting…', 'saving');
        elSubmit.disabled = true;
        try {
            const resp = await fetch(SUBMIT_URL, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify({ answers: state.answers }),
            });
            const data = await resp.json().catch(() => ({}));
            if (resp.ok && data.redirect) {
                window.location.href = data.redirect;
            } else if (resp.ok) {
                window.location.href = RESULTS_URL;
            } else {
                throw new Error(data.error || ('HTTP ' + resp.status));
            }
        } catch (err) {
            setSaveStatus('Submit failed — try again', 'error');
            elSubmit.disabled = false;
        }
    }

    elPrev.addEventListener('click', () => {
        if (state.index > 0) {
            state.index--;
            persist();
            renderQuestion();
            renderProgress();
        }
    });
    elNext.addEventListener('click', () => {
        if (state.index < payload.length - 1) {
            state.index++;
            persist();
            renderQuestion();
            renderProgress();
        }
    });
    elSubmit.addEventListener('click', submit);
    if (elExit) {
        elExit.addEventListener('click', (ev) => {
            if (state.dirty) {
                if (!window.confirm('You have unsaved changes. Leave the Chamber anyway?')) {
                    ev.preventDefault();
                    return;
                }
                persist();
            }
        });
    }
    window.addEventListener('beforeunload', (ev) => {
        if (state.dirty) {
            ev.preventDefault();
            ev.returnValue = '';
        }
    });

    // Kick off
    renderQuestion();
    renderProgress();
    setSaveStatus('Ready', '');
})();
