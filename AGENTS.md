# dbt.thisminute.org

You are the maintainer of dbt.thisminute.org — an encrypted, single-file DBT (Dialectical Behavior Therapy) diary card app with a small relay service for short share links.

## Hard constraints (read these first)

- **`URGES`, `ACTIONS`, and `SKILLS` arrays are append-only.** Their indices are baked into every stored entry and every share URL ever issued. Reordering or removing items silently corrupts all of that. Only append. Never reorder. Never delete.
- **Do not push or deploy directly.** Add an entry to `../ops/DEPLOY_QUEUE.md` with scope `deploy`. The ops orchestrator SCPs `index.html` to `/opt/dbt.thisminute.org/` and the relay files to `/opt/dbt.thisminute.org/relay/` on the VM.
- **No test suite.** Verify changes via static analysis (grep for stale refs, check selectors match) and manual testing in a browser. `start index.html` opens the file directly. No local dev server is set up.

## Architecture

- **Single file**: `index.html` contains all CSS, HTML, and JS
- **JS structure**: Web component definitions at top (outside IIFE), then one large IIFE containing all app logic
- **Encryption**: AES-GCM via Web Crypto API. Multi-vault support — each vault is an isolated diary with its own passphrase
- **Storage**: localStorage only. Entries keyed by date (`YYYY-MM-DD`), encrypted per-vault
- **Theming**: CSS custom properties on `:root` (dark default) with `body.light-mode` overrides
- **Relay**: `relay/app.py` — FastAPI service storing encrypted share payloads with configurable TTL. Runs on port 8050, proxied by nginx at `/api/relay`

## Web Components

Three custom elements with Shadow DOM, defined before the IIFE:

- **`<rating-row>`**: Numeric pill selector (0–N). Used for emotions and urges. Attributes: `label`, `field`, `max`, `type`, `small`
- **`<toggle-row>`**: Tri-state no/yes pills (`null` = unanswered, `false`, `true`). Tapping the selected pill clears it. Unanswered toggles are omitted from the share view. Used for actions and daily toggle categories. Attributes: `label`, `field`
- **`<skill-row>`**: 4 text pills (aware/tried/used/auto) + "helped" toggle. Used for DBT skills. Attributes: `label`, `field`

All three dispatch `field-change` CustomEvents (bubbles, composed) caught by a single centralized listener in `initStaticHandlers()`. State is pushed down via the `.value` property setter.

Attach event listeners once in `connectedCallback()` after `_render()` — never in `_render()` itself.

## Data Model

- **Emotions**: User-defined list in `prefs.emotions`. Stored as `emotion_0`, `emotion_1`, etc. (0–5 intensity)
- **Urges**: Fixed vocabulary in `URGES` array. Stored as `urge_0`, `urge_1`, etc. (0–5 intensity)
- **Actions**: Fixed vocabulary in `ACTIONS` array. Stored by action ID string (boolean)
- **Skills**: Fixed vocabulary in `SKILLS` array of `{ label, desc, similar }` objects (95 items: DBT 0–30, ACT 31–44, CBT 45–57, IFS 58–67, Schema 68–76, CAMS 77–83, CFT 84–88, Somatic 89–94). Stored as `skill_N`. Value encodes engagement × 2 + helped (0–7). `SKILL_CATALOG` is the browsable tree (school → groups → indices) used by the chooser, the daily-card headers, and the share view; `SKILL_META` is the index → school/group back-reference. `similar` links are cross-school and made symmetric at load; they surface only in the info popover, never inside a school's tab. Prefs carry `knownSkillCount` so skills appended later start hidden for existing vaults.
- **Daily**: Sleep (hours + quality), exercise (mins + type), meals (string array), toggle categories (boolean)

## Share Links

Two formats coexist:

- **`#share=PAYLOAD`**: Self-contained. Encrypted payload encoded directly in the URL fragment. Works forever, no server dependency. Can be very long (2K–30K+ chars).
- **`#relay=TOKEN`**: Short link (5-char token). App fetches the encrypted payload from `/api/relay/TOKEN`. Expires after a user-chosen TTL (1 day to 3 months, default 30 days).

Entries between checkpoint and today are serialized to JSON, DEFLATE-compressed, AES-GCM encrypted with a share passphrase, and base64url-encoded.

Share payload format (v2): `{ entries: {...}, hidden: {...} }` when items are hidden, or flat entries object for backward compat when nothing is hidden.

## Relay Service

`relay/app.py` — FastAPI + SQLite. Stores encrypted payloads temporarily.

**Token scheme**: 26 letter prefixes (a–z), each active for 1 week, cycling every 26 weeks. Token = prefix + 4 random alphanumeric chars. When a prefix cycles back, all its old tokens are guaranteed expired. Cleanup runs on each POST.

**Endpoints**:
- `POST /api/relay` — store payload, return token + expiry
- `GET /api/relay/{token}` — retrieve payload or 404 if expired
- `GET /api/relay/health` — status check

## Key Functions

- `buildDynamicSections()`: Creates web component elements for urges/actions/skills/toggle-categories based on vocabulary arrays minus hidden items
- `renderWizardSkills()`: Tabbed skills chooser (one tab per school in `SKILL_CATALOG`); also opened directly from the Skills section via `openWizard('edit', 'skills')`
- `showSkillInfo(idx)`: Info popover for a skill (desc + similar skills), triggered by tapping a skill-row label (`skill-info` event) or the ? button in the chooser
- `renderEmotions()`: Builds emotion rows (rating-row inside .emotion-row wrappers with 7-day avg + hide button)
- `renderEntry()`: Pushes current date's entry values into all web components and static inputs
- `renderShareDayCard()`: Generates HTML string for one day's read-only share view
- `initStaticHandlers()`: Attaches event listeners once — includes the centralized `field-change` handler
- `setupShareUnlock()`: Configures the share passphrase form for both `#share=` and `#relay=` flows

## Working style

This is a personal therapeutic tool. Treat it accordingly: small focused changes over sweeping rewrites, careful when touching anything that could affect stored entries or share URLs, no telemetry of any kind, no third-party dependencies in the frontend. The encryption is what makes the project meaningful — never weaken it, never log decrypted content, never bypass passphrase prompts.
