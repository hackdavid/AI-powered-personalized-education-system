# Admin setup — AppSetting keys to configure after install

One-time checklist for the **admin** (the person with `superuser` access)
to configure runtime settings through Django admin. Team-mates never
touch these — they're shared from the DB.

## Where

Once the platform is running, visit:

```
http://127.0.0.1:8000/admin/core/appsetting/
```

You'll see 10 rows auto-created by `bootstrap_app_settings`. Click each
key, paste the right value, tick **Is active**, Save. Then restart the
server — values are applied by `CoreConfig.ready()` on boot.

## Full list of keys (10)

Grouped by category, mirroring the `Category` choices on `AppSetting`.

### 🔑 LLM — chat completion for the tutor

| Key | Value to set | Required? | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | `sk-...` (your OpenAI key) | **No** — off = offline stub | When blank / inactive, the tutor falls back to a stub that just lists the retrieved sources. That's fine for demos. Paste a real key when you want grounded natural-language answers. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | yes (default) | Swap for Azure OpenAI / Ollama / any OpenAI-compatible endpoint. |
| `OPENAI_MODEL_NAME` | `gpt-4o-mini` (recommended) / `gpt-4` / `gpt-3.5-turbo` | yes | Cheaper models work fine for our use case. Ask in the team chat if unsure. |
| `ANTHROPIC_API_KEY` | (leave blank) | no | Optional fallback. Not used yet. |
| `LLM_PROVIDER` | `openai` | yes | Only `openai` supported today. |

**Offline mode** (recommended while we're still in dev): leave
`OPENAI_API_KEY` inactive. Tutor stays in stub mode. Zero LLM bill.

### 🧠 Embedding — vector generation

| Key | Value to set | Required? | Notes |
|---|---|---|---|
| `EMBEDDING_PROVIDER` | `remote` | yes | Stay on `remote` unless someone can't reach the HF Space. |
| `EMBEDDER_API_URL` | `https://ibrahimdaud-text-embding-model.hf.space` | yes | URL of the shared HuggingFace Space. Don't change without redeploying. |
| `EMBEDDER_API_KEY` | (the 43-char token generated when the Space was set up) | yes | Same token is set as a secret in the Space's settings. Rotate together. |
| `EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | yes | Must match the model running in the HF Space. Changing this = re-embed everything (different dim). |

### 🗃️ Vector store

| Key | Value to set | Required? | Notes |
|---|---|---|---|
| `VECTOR_STORE_TYPE` | `pgvector` | yes | Only value supported today. Ships with the Supabase DB. |

## Which to activate vs leave inactive

On a fresh bootstrap, rows land in this state:

| Key | Active on fresh boot? | What you do |
|---|---|---|
| `OPENAI_BASE_URL` | ✓ active | leave it |
| `OPENAI_MODEL_NAME` | ✓ active | leave it |
| `LLM_PROVIDER` | ✓ active | leave it |
| `EMBEDDING_PROVIDER` | ✓ active | leave it |
| `EMBEDDER_API_URL` | ✓ active | leave it |
| `EMBEDDER_API_KEY` | ✓ active | leave it |
| `EMBEDDING_MODEL_NAME` | ✓ active | leave it |
| `VECTOR_STORE_TYPE` | ✓ active | leave it |
| `OPENAI_API_KEY` | ✗ inactive (blank) | paste + activate when you want real LLM answers |
| `ANTHROPIC_API_KEY` | ✗ inactive (blank) | leave it |

So **8 active, 2 inactive** is the happy "offline mode" default. You don't
have to touch anything for the tutor to start returning grounded sources —
just from pgvector + the stub answerer.

## Checklist for turning on the real LLM later

When you decide to flip on real OpenAI answers:

- [ ] Go to `/admin/core/appsetting/`
- [ ] Click the `OPENAI_API_KEY` row
- [ ] Paste your OpenAI key in the `Value` field
- [ ] Tick **Is active**
- [ ] Save
- [ ] Restart the server (`Ctrl+C` → `python manage.py runserver`)
- [ ] Boot log should show `Applied 9 AppSetting override(s)...` (was 8)
- [ ] Log in as a seeded student, ask a question — answer now reads like a tutor, not a list of sources

To go back to offline mode: untick **Is active** on `OPENAI_API_KEY`,
save, restart. Value stays in the DB (doesn't get wiped).

## Editing semantics

- **Values are strings only.** Don't try to put booleans / integers
  here — they'd be set as the literal strings `'True'` / `'42'` and
  break comparisons.
- **Changes take effect on server restart.** By design; `runserver` reload
  on file changes doesn't pick up DB changes.
- **Secrets are masked in the list view** (only last 4 chars shown).
  Detail view shows plaintext — admin is staff-only.
- **Audit**: every save records `updated_by` + `updated_at` on the row.
- **Never commit actual values to git.** If you need to share values with
  another admin, send them via a secret-sharing tool, not git.

## Rotating secrets

1. Update the external service (generate a new OpenAI key / rotate the
   HF Space secret).
2. Paste the new value into the matching `AppSetting` row and save.
3. Restart the server.
4. Old key becomes useless immediately at the external service.

No code changes, no other team-mate needs to update anything — they read
from the same DB.
