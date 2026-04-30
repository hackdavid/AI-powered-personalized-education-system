/* ==========================================================================
   Student AI-tutor chat page — frontend controller.
   --------------------------------------------------------------------------

   Responsibilities:
     * Hydrate an active session from `/api/v1/tutoring/sessions/<id>/`
     * Send questions to `/api/v1/tutoring/sessions/<id>/messages/stream/`
       (Server-Sent Events) and render tokens live
     * Render Markdown + LaTeX + code + tables via marked → DOMPurify → KaTeX
     * Replace "[N]" citation tokens with clickable chips that:
         - hover-preview the source snippet
         - scroll to the matching source row on click
     * Provide a modern composer (auto-grow, Enter to send, Shift+Enter = nl)
     * Copy / regenerate actions on each assistant turn

   The file is intentionally self-contained (no modules) because the rest of
   the project loads plain scripts via `<script>` tags. All external libs
   (marked, DOMPurify, KaTeX, highlight.js) are pulled in from the template.
   ========================================================================== */

(function () {
    'use strict';

    const API_ROOT = '/api/v1/tutoring/sessions/';

    // ------------------------------ DOM refs

    // `.chat-app` is the outer grid in the redesigned template. (`.chat-shell`
    // was the old class — kept here as a fallback so the script doesn't break
    // if someone loads a cached template while deploying.)
    const shell = document.querySelector('.chat-app') || document.querySelector('.chat-shell');
    if (!shell) return;

    const sessionId = shell.dataset.sessionId || null;
    const newSessionBaseUrl = shell.dataset.newSessionUrl || '/student/chat/';

    const messagesBody = document.getElementById('messages-body');
    const composer = document.getElementById('composer');
    const composerInput = document.getElementById('composer-input');
    const composerSend = document.getElementById('composer-send');
    const scrollBtn = document.getElementById('btn-scroll-bottom');

    const newSessionBtn = document.getElementById('btn-new-session');
    const emptyNewBtn = document.getElementById('btn-empty-new-session');
    const tooltipEl = document.getElementById('citation-tooltip');

    // ------------------------------ Markdown / KaTeX setup

    // marked: turn source Markdown into HTML. GFM on, smartypants off (the LLM
    // sometimes emits `$...$` and we don't want marked's smartquotes chewing
    // the dollar signs before KaTeX sees them).
    if (window.marked) {
        window.marked.setOptions({
            gfm: true,
            breaks: false,
            smartypants: false,
            mangle: false,
            headerIds: false,
        });
    }

    function renderMarkdown(raw) {
        if (!window.marked || !window.DOMPurify) return escapeHtml(raw || '');
        const normalized = normalizeMath(raw || '');
        const html = window.marked.parse(normalized, { async: false });
        return window.DOMPurify.sanitize(html, {
            USE_PROFILES: { html: true, mathMl: false, svg: false },
            ADD_ATTR: ['target', 'rel'],
        });
    }

    // ------------------------------ math shorthand normaliser

    /**
     * Turn common "programmer shorthand" math into LaTeX KaTeX can render.
     *
     * This is a SAFETY NET for the rare case the LLM slips out of the
     * LaTeX rules from the system prompt (e.g. `sqrt(b^2 - 4ac)` instead
     * of `$\sqrt{b^2 - 4ac}$`). The primary fix is always the prompt.
     *
     * Strategy:
     *   1. Protect existing code blocks / inline code / math delimiters
     *      so we never double-wrap or touch legitimate code identifiers.
     *   2. On the remaining "plain" text, apply conservative replacements:
     *        - `sqrt(expr)`               → `$\sqrt{expr}$`
     *        - bare `\frac{a}{b}`, `\sum`, `\int`, `\lim`, `\alpha` etc. → wrap in `$...$`
     *        - `base^exp` (single-letter / paren base, numeric / braced exp) → wrap
     *   3. Restore protected segments.
     *
     * We deliberately DO NOT attempt to auto-wrap whole equations. That is
     * brittle and produces false positives on prose like "see page 4".
     */
    function normalizeMath(markdown) {
        if (!markdown) return markdown;

        const stash = [];
        const PLACEHOLDER = (i) => `\u0001MATH${i}\u0001`;
        // Single regex that matches every span we never want to touch:
        // fenced code, inline code, $$...$$, \[..\], \(..\), $...$.
        const PROTECT_RE =
            /(```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+?\$)/g;

        const protectAll = () => {
            markdown = markdown.replace(PROTECT_RE, (m) => {
                stash.push(m);
                return PLACEHOLDER(stash.length - 1);
            });
        };
        // Protect once before any transformation.
        protectAll();

        // Each transformation is followed by another `protectAll()` pass so
        // the `$...$` wrappers it just created cannot be re-matched by the
        // next transformation (which is how `$\sqrt{b^2 - 4ac}$` used to
        // end up with its inner `b^2` re-wrapped into `$b^{2}$`).

        // 2a. `sqrt(expr)` → `$\sqrt{expr}$`. One level of nested parens.
        markdown = markdown.replace(
            /\bsqrt\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)/g,
            (_m, inner) => `$\\sqrt{${inner}}$`,
        );
        protectAll();

        // 2b. Bare LaTeX commands with braces — wrap in `$...$`.
        //     Covers \frac{..}{..}, \sqrt{..}, \sum_{..}^{..}, \int_{..}^{..},
        //     \lim_{..}, \binom{..}{..}.
        markdown = markdown.replace(
            /(?<![$\\a-zA-Z])\\(?:frac|sqrt|sum|int|prod|lim|binom)(?:\[[^\]]*\])?\{[^{}]*\}(?:\{[^{}]*\})?/g,
            (m) => `$${m}$`,
        );
        protectAll();

        // 2c. Bare LaTeX Greek / operator macros — wrap in `$...$`.
        markdown = markdown.replace(
            /(?<![$\\a-zA-Z])\\(?:alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|omicron|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega|Alpha|Beta|Gamma|Delta|Theta|Lambda|Pi|Sigma|Phi|Omega|pm|times|cdot|infty|to|neq|leq|geq|approx|ldots|cdots)\b/g,
            (m) => `$${m}$`,
        );
        protectAll();

        // 2d. `base^exp` shorthand → `$base^{exp}$`.
        //     Base: single letter / digit / closing paren. Exp: digits or `{...}`.
        //     Deliberately narrow — keeps prose like "see page 4" alone.
        markdown = markdown.replace(
            /([A-Za-z0-9)])\^(\{[^}]+\}|\d+)/g,
            (_m, base, exp) => {
                const braced = exp.startsWith('{') ? exp : `{${exp}}`;
                return `$${base}^${braced}$`;
            },
        );

        // Step 3 — Restore protected segments.
        markdown = markdown.replace(/\u0001MATH(\d+)\u0001/g, (_m, i) => stash[Number(i)]);
        return markdown;
    }

    function renderMathIn(el) {
        if (!window.renderMathInElement || !el) return;
        try {
            window.renderMathInElement(el, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '\\[', right: '\\]', display: true },
                    { left: '$',  right: '$',  display: false },
                    { left: '\\(', right: '\\)', display: false },
                ],
                throwOnError: false,
                ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
            });
        } catch (err) {
            // Non-fatal — KaTeX will log its own errors. We keep the raw text.
        }
    }

    function highlightCodeIn(el) {
        if (!window.hljs || !el) return;
        el.querySelectorAll('pre code').forEach(block => {
            try { window.hljs.highlightElement(block); } catch (_) { /* noop */ }
        });
    }

    function addCopyButtonsTo(el) {
        if (!el) return;
        el.querySelectorAll('pre').forEach(pre => {
            if (pre.querySelector('.chat-code-copy')) return;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'chat-code-copy';
            btn.textContent = 'Copy';
            btn.addEventListener('click', async () => {
                const code = pre.querySelector('code');
                const text = code ? code.innerText : pre.innerText;
                try {
                    await navigator.clipboard.writeText(text);
                    btn.textContent = 'Copied ✓';
                } catch (_) {
                    btn.textContent = 'Error';
                }
                setTimeout(() => { btn.textContent = 'Copy'; }, 1400);
            });
            pre.appendChild(btn);
        });
    }

    // ------------------------------ generic helpers

    function escapeHtml(str) {
        return (str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function el(tag, attrs = {}, children = []) {
        const node = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => {
            if (v === false || v === null || v === undefined) return;
            if (k === 'className') node.className = v;
            else if (k === 'dataset' && typeof v === 'object') {
                Object.entries(v).forEach(([dk, dv]) => { node.dataset[dk] = dv; });
            }
            else if (k.startsWith('on') && typeof v === 'function') {
                node.addEventListener(k.slice(2).toLowerCase(), v);
            }
            else node.setAttribute(k, v);
        });
        (Array.isArray(children) ? children : [children]).forEach(c => {
            if (c == null) return;
            node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        });
        return node;
    }

    function scrollToBottom(force = false) {
        if (!messagesBody) return;
        const nearBottom = messagesBody.scrollHeight - messagesBody.scrollTop - messagesBody.clientHeight < 80;
        if (force || nearBottom) {
            messagesBody.scrollTop = messagesBody.scrollHeight;
        }
    }

    // ------------------------------ citation substitution

    /**
     * Walk the rendered answer DOM and replace any `[N]` tokens found in
     * TEXT nodes (not inside code/pre) with a clickable citation chip.
     * Keeping the replacement in text-nodes means we never corrupt
     * KaTeX's rendered math or highlighted code.
     */
    function replaceCitationsIn(contentEl, sourcesByIndex) {
        if (!contentEl) return;
        const walker = document.createTreeWalker(
            contentEl,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode(node) {
                    const parent = node.parentElement;
                    if (!parent) return NodeFilter.FILTER_REJECT;
                    const tag = parent.tagName;
                    if (tag === 'CODE' || tag === 'PRE' || tag === 'SCRIPT') {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (parent.classList.contains('katex') || parent.closest('.katex')) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return /\[\d+\]/.test(node.nodeValue)
                        ? NodeFilter.FILTER_ACCEPT
                        : NodeFilter.FILTER_REJECT;
                },
            },
        );

        const textNodes = [];
        let n;
        while ((n = walker.nextNode())) textNodes.push(n);

        textNodes.forEach(textNode => {
            const text = textNode.nodeValue;
            const regex = /\[(\d+)\]/g;
            let match;
            let lastIndex = 0;
            const frag = document.createDocumentFragment();

            while ((match = regex.exec(text)) !== null) {
                if (match.index > lastIndex) {
                    frag.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
                }
                const idx = Number(match[1]);
                const hasSource = sourcesByIndex && sourcesByIndex[idx];
                if (hasSource) {
                    const chip = el('span', {
                        className: 'chat-citation',
                        dataset: { citation: String(idx) },
                        role: 'button',
                        tabindex: '0',
                    }, [String(idx)]);
                    frag.appendChild(chip);
                } else {
                    frag.appendChild(document.createTextNode(match[0]));
                }
                lastIndex = match.index + match[0].length;
            }
            if (lastIndex < text.length) {
                frag.appendChild(document.createTextNode(text.slice(lastIndex)));
            }
            textNode.parentNode.replaceChild(frag, textNode);
        });
    }

    // ------------------------------ source helpers

    function sourcesByIndex(sources) {
        const map = {};
        (sources || []).forEach((src, i) => { map[i + 1] = src; });
        return map;
    }

    function buildSourcesBlock(sources) {
        if (!sources || !sources.length) return null;

        const listItems = sources.map((src, i) => {
            const idx = i + 1;
            const page = src.page_number ? ` · p. ${src.page_number}` : '';
            const subject = src.subject_name ? ` · ${src.subject_name}` : '';
            const titleText = src.title || src.document_title || 'Source';

            return el('div', {
                className: 'chat-source-row',
                dataset: { source: String(idx) },
            }, [
                el('div', { className: 'chat-source-row__head' }, [
                    el('span', { className: 'chat-source-row__index' }, [`[${idx}]`]),
                    el('span', { className: 'chat-source-row__title' }, [titleText]),
                    el('span', { className: 'chat-source-row__meta' }, [
                        (src.document_title && src.document_title !== titleText ? src.document_title : '') +
                        subject + page,
                    ]),
                ]),
                el('div', { className: 'chat-source-row__snippet' }, [src.snippet || '']),
            ]);
        });

        const caret = el('span', { className: 'chat-sources__caret' }, ['▾']);
        const header = el('div', { className: 'chat-sources__header' }, [
            el('h4', { className: 'chat-sources__title' }, [`Sources · ${sources.length}`]),
            caret,
        ]);
        const list = el('div', { className: 'chat-sources__list' }, listItems);
        const wrapper = el('div', { className: 'chat-sources' }, [header, list]);

        header.addEventListener('click', () => {
            wrapper.classList.toggle('is-collapsed');
        });

        list.addEventListener('click', (e) => {
            const row = e.target.closest('.chat-source-row');
            if (row) row.classList.toggle('is-open');
        });

        return wrapper;
    }

    // ------------------------------ routing chip

    const SUBJECT_ICON = '<svg xmlns="http://www.w3.org/2000/svg" class="chat-routing-chip__icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"/></svg>';

    function buildRoutingChip(routing) {
        if (!routing) return null;
        const subjects = routing.subject_names || [];
        const topics = routing.topic_titles || [];
        const intent = routing.intent || '';

        // Don't show a chip for chitchat / meta — the reply is already short.
        if (!subjects.length && (intent === 'chitchat' || intent === 'meta' || intent === 'other')) {
            return null;
        }

        const chip = document.createElement('span');
        chip.className = 'chat-routing-chip';
        chip.innerHTML = SUBJECT_ICON;

        const subjectEl = document.createElement('span');
        subjectEl.className = 'chat-routing-chip__subject';
        subjectEl.textContent = subjects.length ? subjects.join(' · ') : 'General';
        chip.appendChild(subjectEl);

        if (topics.length) {
            const topicEl = document.createElement('span');
            topicEl.className = 'chat-routing-chip__topic';
            topicEl.textContent = ' · ' + topics.join(', ');
            chip.appendChild(topicEl);
        }

        return chip;
    }

    // ------------------------------ general-knowledge notice

    const INFO_ICON = '<svg xmlns="http://www.w3.org/2000/svg" class="chat-notice__icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';

    /**
     * Show a small notice above the answer when the router intended to
     * retrieve curriculum context but pgvector returned zero hits. The
     * answer is still real LLM output — it just isn't grounded in the
     * student's curriculum, so we tell them that.
     */
    function buildGeneralKnowledgeNotice() {
        const notice = document.createElement('div');
        notice.className = 'chat-notice';
        notice.innerHTML = INFO_ICON;
        const body = document.createElement('div');
        body.innerHTML = '<strong>Heads up — general knowledge answer.</strong> '
            + "I couldn't find a specific match in your curriculum for this "
            + 'question, so this answer is based on general knowledge and has '
            + 'no source citations.';
        notice.appendChild(body);
        return notice;
    }

    function isGeneralKnowledgeAnswer(routing, sources) {
        if (!routing) return false;
        if (!routing.needs_retrieval) return false;       // chitchat/meta path
        return !sources || sources.length === 0;
    }

    // ------------------------------ message rendering

    /**
     * Build and return a DOM element for a chat message. Returns a handle
     * object with helpers for the streaming flow (update content, set
     * sources, show thinking indicator, etc.).
     */
    function buildMessageEl(msg) {
        const isStudent = msg.role === 'student';
        const cls = isStudent ? 'chat-message--student' : 'chat-message--assistant';

        const container = el('div', {
            className: `chat-message ${cls}`,
            dataset: { messageId: String(msg.id || '') },
        });

        const bubble = el('div', { className: 'chat-bubble' });

        if (!isStudent) {
            // Meta row: avatar + label + model badge
            const meta = el('div', { className: 'chat-bubble__meta' }, [
                el('span', { className: 'chat-bubble__avatar' }, ['AI']),
                el('span', {}, ['Tutor']),
            ]);
            bubble.appendChild(meta);

            // Routing chip slot (populated later when routing arrives)
            const chipSlot = el('div', { className: 'chat-bubble__routing-slot' });
            bubble.appendChild(chipSlot);

            // General-knowledge notice slot (populated when sources is empty
            // but the router asked for retrieval).
            const noticeSlot = el('div', { className: 'chat-bubble__notice-slot' });
            bubble.appendChild(noticeSlot);
        }

        const content = el('div', { className: 'chat-bubble__content' });
        bubble.appendChild(content);

        container.appendChild(bubble);

        // Student turns are plain text; assistant turns get rendered Markdown.
        if (isStudent) {
            content.textContent = msg.content || '';
        } else {
            hydrateAssistantContent(container, content, msg.content || '', msg.retrieved_chunks || [],
                (msg.metadata && msg.metadata.routing) || null);
        }

        const api = {
            root: container,
            contentEl: content,
            bubbleEl: bubble,
            rawText: msg.content || '',

            appendToken(piece) {
                this.rawText += piece;
                // Re-render full markdown on each token — cheap for chat-length
                // content and keeps formatting (tables, lists, math) consistent.
                hydrateAssistantContent(this.root, this.contentEl, this.rawText, this._sources, this._routing);
            },
            finalize(finalText) {
                if (typeof finalText === 'string' && finalText.length) {
                    this.rawText = finalText;
                }
                hydrateAssistantContent(this.root, this.contentEl, this.rawText, this._sources, this._routing);
                addAssistantActions(this.bubbleEl, this.rawText);
                if (this._sources && this._sources.length) {
                    this.setSources(this._sources);
                }
                this._refreshNotice();
            },
            setRouting(routing) {
                this._routing = routing;
                const slot = this.bubbleEl.querySelector('.chat-bubble__routing-slot');
                if (slot) {
                    slot.innerHTML = '';
                    const chip = buildRoutingChip(routing);
                    if (chip) slot.appendChild(chip);
                }
                this._refreshNotice();
            },
            setSources(sources) {
                this._sources = sources;
                // Strip any existing sources block and re-add so counts stay accurate.
                this.bubbleEl.querySelectorAll('.chat-sources').forEach(s => s.remove());
                const block = buildSourcesBlock(sources);
                if (block) this.bubbleEl.appendChild(block);
                // Re-run citation substitution now that we know the mapping.
                rehydrateCitations(this.contentEl, sources);
                this._refreshNotice();
            },
            _refreshNotice() {
                const slot = this.bubbleEl.querySelector('.chat-bubble__notice-slot');
                if (!slot) return;
                slot.innerHTML = '';
                if (isGeneralKnowledgeAnswer(this._routing, this._sources)) {
                    slot.appendChild(buildGeneralKnowledgeNotice());
                }
            },
        };

        // Stash default state so incremental updates work.
        api._sources = msg.retrieved_chunks || [];
        api._routing = (msg.metadata && msg.metadata.routing) || null;
        if (!isStudent) {
            if (api._routing) api.setRouting(api._routing);
            api._refreshNotice();
        }
        return api;
    }

    function hydrateAssistantContent(root, contentEl, rawMarkdown, sources, routing) {
        contentEl.innerHTML = renderMarkdown(rawMarkdown);
        highlightCodeIn(contentEl);
        addCopyButtonsTo(contentEl);
        renderMathIn(contentEl);
        if (sources && sources.length) {
            replaceCitationsIn(contentEl, sourcesByIndex(sources));
        }
    }

    function rehydrateCitations(contentEl, sources) {
        // Undo previous citation chips (render from rawText is cheaper; but
        // we don't keep rawText for history rendering, so just rebuild).
        contentEl.querySelectorAll('.chat-citation').forEach(chip => {
            chip.replaceWith(document.createTextNode(`[${chip.dataset.citation}]`));
        });
        replaceCitationsIn(contentEl, sourcesByIndex(sources));
    }

    function addAssistantActions(bubble, rawText) {
        if (!bubble || bubble.querySelector('.chat-bubble__actions')) return;

        const copyBtn = el('button', {
            type: 'button',
            className: 'chat-action-btn',
            title: 'Copy answer',
        }, [
            el('span', {}, ['Copy']),
        ]);
        copyBtn.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(rawText);
                copyBtn.classList.add('is-success');
                copyBtn.querySelector('span').textContent = 'Copied ✓';
                setTimeout(() => {
                    copyBtn.classList.remove('is-success');
                    copyBtn.querySelector('span').textContent = 'Copy';
                }, 1400);
            } catch (_) { /* ignore clipboard failures */ }
        });

        const actions = el('div', { className: 'chat-bubble__actions' }, [copyBtn]);
        bubble.appendChild(actions);
    }

    // ------------------------------ thinking indicator

    function buildThinkingEl() {
        return el('div', { className: 'chat-message chat-message--assistant', dataset: { thinking: '1' } }, [
            el('div', { className: 'chat-thinking' }, [
                el('span', {}, ['Thinking']),
                el('span', { className: 'chat-thinking__dots' }, [
                    el('span', {}, []),
                    el('span', {}, []),
                    el('span', {}, []),
                ]),
            ]),
        ]);
    }

    // ------------------------------ citation tooltip wiring

    function attachTooltipHandlers() {
        if (!messagesBody || messagesBody.dataset.tooltipBound === '1') return;
        messagesBody.dataset.tooltipBound = '1';

        messagesBody.addEventListener('mouseover', (e) => {
            const chip = e.target.closest('.chat-citation');
            if (!chip) return;
            const idx = Number(chip.dataset.citation);
            const bubble = chip.closest('.chat-bubble');
            if (!bubble) return;
            const row = bubble.querySelector(`.chat-source-row[data-source="${idx}"]`);
            if (!row) return;
            const title = row.querySelector('.chat-source-row__title');
            const snippet = row.querySelector('.chat-source-row__snippet');
            const meta = row.querySelector('.chat-source-row__meta');
            tooltipEl.innerHTML = '';
            if (title) tooltipEl.appendChild(el('strong', {}, [title.textContent]));
            if (meta && meta.textContent.trim()) tooltipEl.appendChild(el('em', {}, [meta.textContent]));
            if (snippet && snippet.textContent.trim()) {
                const snip = document.createElement('div');
                snip.textContent = snippet.textContent.length > 280
                    ? snippet.textContent.slice(0, 277) + '…'
                    : snippet.textContent;
                tooltipEl.appendChild(snip);
            }
            const rect = chip.getBoundingClientRect();
            const top = rect.top - 12;
            const left = Math.min(window.innerWidth - 380, Math.max(8, rect.left));
            tooltipEl.style.top = `${top}px`;
            tooltipEl.style.left = `${left}px`;
            tooltipEl.style.transform = 'translateY(-100%)';
            tooltipEl.classList.add('is-visible');
            tooltipEl.setAttribute('aria-hidden', 'false');
        });

        messagesBody.addEventListener('mouseout', (e) => {
            if (e.target.closest && e.target.closest('.chat-citation')) {
                tooltipEl.classList.remove('is-visible');
                tooltipEl.setAttribute('aria-hidden', 'true');
            }
        });

        messagesBody.addEventListener('click', (e) => {
            const chip = e.target.closest('.chat-citation');
            if (!chip) return;
            e.preventDefault();
            const idx = chip.dataset.citation;
            const bubble = chip.closest('.chat-bubble');
            if (!bubble) return;
            const row = bubble.querySelector(`.chat-source-row[data-source="${idx}"]`);
            if (!row) return;
            const wrapper = row.closest('.chat-sources');
            if (wrapper) wrapper.classList.remove('is-collapsed');
            bubble.querySelectorAll('.chat-source-row').forEach(r => r.classList.remove('is-targeted'));
            bubble.querySelectorAll('.chat-citation').forEach(c => c.classList.remove('is-targeted'));
            row.classList.add('is-targeted', 'is-open');
            chip.classList.add('is-targeted');
            row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    }

    // ------------------------------ history load

    async function loadSessionHistory() {
        if (!sessionId || !messagesBody) return;

        const result = await APIClient.get(`${API_ROOT}${sessionId}/`, null, { showSuccessToast: false });
        if (!result.success) {
            messagesBody.innerHTML = '<div class="chat-error">Could not load this conversation.</div>';
            return;
        }
        const messages = (result.data && result.data.messages) || [];

        messagesBody.innerHTML = '';
        if (!messages.length) {
            messagesBody.innerHTML = '<div class="chat-loading">Ask your first question to get started.</div>';
            return;
        }
        messages.forEach(m => {
            const h = buildMessageEl(m);
            messagesBody.appendChild(h.root);
            if (m.role === 'assistant') {
                h.finalize(m.content || '');
            }
        });
        scrollToBottom(true);
    }

    // ------------------------------ streaming send

    function getCsrf() {
        return APIClient.getCSRFToken ? APIClient.getCSRFToken() : '';
    }

    async function streamMessage(content) {
        if (!sessionId) return;

        composerSend.disabled = true;

        // Drop the "ask your first question" placeholder if present.
        const placeholder = messagesBody.querySelector('.chat-loading');
        if (placeholder) placeholder.remove();

        // Optimistic user turn (replaced by server payload when it arrives).
        const optimisticId = `tmp-${Date.now()}`;
        const studentHandle = buildMessageEl({
            id: optimisticId,
            role: 'student',
            content,
        });
        messagesBody.appendChild(studentHandle.root);
        scrollToBottom(true);

        // Thinking indicator sits in the assistant slot until tokens arrive.
        const thinkingEl = buildThinkingEl();
        messagesBody.appendChild(thinkingEl);
        scrollToBottom(true);

        let assistantHandle = null;
        let finalAssistantMessage = null;

        const ensureAssistant = () => {
            if (assistantHandle) return assistantHandle;
            // Swap the thinking indicator out for a real assistant bubble.
            const fresh = buildMessageEl({ id: 'tmp-assistant', role: 'assistant', content: '' });
            thinkingEl.replaceWith(fresh.root);
            assistantHandle = fresh;
            return assistantHandle;
        };

        try {
            const response = await fetch(`${API_ROOT}${sessionId}/messages/stream/`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                    'X-CSRFToken': getCsrf(),
                },
                body: JSON.stringify({ content }),
            });

            if (!response.ok || !response.body) {
                throw new Error(`Stream request failed (${response.status})`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                // Split on SSE frame boundary (\n\n) and process full frames.
                const frames = buffer.split('\n\n');
                buffer = frames.pop() || '';

                for (const frame of frames) {
                    if (!frame.trim()) continue;
                    const evt = parseSseFrame(frame);
                    if (!evt) continue;

                    switch (evt.event) {
                        case 'user_message':
                            if (evt.data && evt.data.id) {
                                studentHandle.root.dataset.messageId = String(evt.data.id);
                            }
                            break;

                        case 'routing':
                            ensureAssistant().setRouting(evt.data);
                            scrollToBottom();
                            break;

                        case 'sources':
                            ensureAssistant().setSources(evt.data || []);
                            scrollToBottom();
                            break;

                        case 'token':
                            ensureAssistant().appendToken(evt.data || '');
                            scrollToBottom();
                            break;

                        case 'title':
                            // LLM-refined session title after the first round.
                            // Updates the chat header + sidebar row in place.
                            if (evt.data && evt.data.title) {
                                applySessionTitle(evt.data.title);
                            }
                            break;

                        case 'done':
                            finalAssistantMessage = evt.data || {};
                            break;

                        case 'error':
                            if (!assistantHandle) {
                                ensureAssistant();
                            }
                            assistantHandle.appendToken(`\n\n_${evt.data || 'Something went wrong.'}_`);
                            break;

                        case 'close':
                        default:
                            break;
                    }
                }
            }
        } catch (err) {
            console.error('streaming failed', err);
            if (!assistantHandle) {
                ensureAssistant();
            }
            assistantHandle.appendToken(
                '\n\n_The connection to the tutor was interrupted. Please try again._',
            );
        }

        // Finalise: stamp the real ids / sources / title.
        if (finalAssistantMessage && finalAssistantMessage.assistant_message) {
            const am = finalAssistantMessage.assistant_message;
            const handle = ensureAssistant();
            handle.root.dataset.messageId = String(am.id);
            handle.rawText = am.content || handle.rawText;
            handle._sources = finalAssistantMessage.sources || handle._sources || [];
            handle._routing = finalAssistantMessage.routing || handle._routing;
            handle.setRouting(handle._routing);
            handle.finalize(handle.rawText);

            // `done` also carries the session (id, title, title_changed).
            // Update sidebar + header if the title hasn't been applied yet
            // via an earlier `title` event.
            const sess = finalAssistantMessage.session;
            if (sess && sess.title) applySessionTitle(sess.title);
        } else if (assistantHandle) {
            assistantHandle.finalize(assistantHandle.rawText);
        } else if (thinkingEl && thinkingEl.parentNode) {
            // No tokens ever arrived — replace the thinking indicator with a fallback.
            const fallback = buildMessageEl({
                id: 'tmp-assistant',
                role: 'assistant',
                content: 'I could not generate an answer. Please try again.',
            });
            thinkingEl.replaceWith(fallback.root);
            fallback.finalize(fallback.rawText);
        }

        composerSend.disabled = false;
        composerInput.focus();
        scrollToBottom();
    }

    /**
     * Apply a freshly-generated session title to every place it can appear:
     *   * the chat header (h1)
     *   * the active row in the sidebar list
     *   * the browser tab title
     *
     * Safe to call multiple times — no-op if the new title matches.
     */
    function applySessionTitle(newTitle) {
        const title = (newTitle || '').trim();
        if (!title || !sessionId) return;

        const header = document.getElementById('chat-title');
        if (header && header.textContent !== title) {
            header.textContent = title;
        }

        // Sidebar row for THIS session.
        const row = document.querySelector(
            `.chat-session[data-session-id="${sessionId}"] .chat-session__title`
        );
        if (row && row.textContent.trim() !== title) {
            row.textContent = title;
        }

        // Browser tab.
        if (document.title.indexOf(title) === -1) {
            document.title = `${title} · AI Tutor · EduAI`;
        }
    }

    function parseSseFrame(frame) {
        // Lines come as `event: X\ndata: Y`. Only the first of each type
        // is honoured (we never emit multiple in a single frame).
        const lines = frame.split('\n');
        let event = 'message';
        const dataLines = [];
        for (const line of lines) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
        }
        const raw = dataLines.join('\n');
        let data = raw;
        if (raw) {
            try { data = JSON.parse(raw); } catch (_) { /* keep as string */ }
        }
        return { event, data };
    }

    // ------------------------------ composer wiring

    function autoGrow(textarea) {
        if (!textarea) return;
        textarea.style.height = 'auto';
        textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
    }

    if (composerInput) {
        composerInput.addEventListener('input', () => autoGrow(composerInput));
        composerInput.addEventListener('keydown', (e) => {
            // Enter submits; Shift+Enter inserts a newline.
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                composer.requestSubmit();
            }
        });
    }

    if (composer) {
        composer.addEventListener('submit', (e) => {
            e.preventDefault();
            const text = (composerInput.value || '').trim();
            if (!text) return;
            composerInput.value = '';
            autoGrow(composerInput);
            streamMessage(text);
        });
    }

    if (scrollBtn) {
        scrollBtn.addEventListener('click', () => scrollToBottom(true));
    }

    // ------------------------------ "New chat" — no more modal

    async function startNewSession() {
        const result = await APIClient.post(API_ROOT, {}, { showSuccessToast: false });
        if (result.success && result.data && result.data.id) {
            const base = newSessionBaseUrl.replace(/\/$/, '');
            window.location.href = `${base}/${result.data.id}/`;
        }
    }

    if (newSessionBtn) newSessionBtn.addEventListener('click', startNewSession);
    if (emptyNewBtn)   emptyNewBtn.addEventListener('click', startNewSession);

    document.querySelectorAll('.chat-app__empty-suggestion, .chat-empty__suggestion').forEach(btn => {
        btn.addEventListener('click', async () => {
            const suggestion = btn.dataset.suggestion || '';
            const result = await APIClient.post(API_ROOT, {}, { showSuccessToast: false });
            if (result.success && result.data && result.data.id) {
                const base = newSessionBaseUrl.replace(/\/$/, '');
                // Stash the suggestion so the new page sends it immediately.
                sessionStorage.setItem('chat:first-message', suggestion);
                window.location.href = `${base}/${result.data.id}/`;
            }
        });
    });

    // ------------------------------ boot

    if (sessionId) {
        attachTooltipHandlers();
        loadSessionHistory().then(() => {
            if (composerInput) composerInput.focus();
            // If the user came in via a suggestion chip, auto-send.
            const first = sessionStorage.getItem('chat:first-message');
            if (first) {
                sessionStorage.removeItem('chat:first-message');
                composerInput.value = first;
                composer.requestSubmit();
            }
        });
    }
})();
