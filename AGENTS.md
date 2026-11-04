# dbt.thisminute.org

You are the maintainer of dbt.thisminute.org — an encrypted, single-file DBT (Dialectical Behavior Therapy) diary card app with a small relay service for short share links.

## Hard constraints (read these first)

- **`URGES`, `SKILLS`, `SCHEMAS`, `CATEGORIES` and `DEFAULT_EMOTIONS` are append-only.** Their indices / ids are baked into every stored entry and every share URL ever issued. Reordering or removing items silently corrupts all of that. Only append. Never reorder. Never delete. Same for a vault's `prefs.emotions` and `prefs.parts` lists (display order is computed separately).
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

Four custom elements with Shadow DOM, defined before the IIFE:

- **`<rating-row>`**: Numeric pill selector (0–N). Used for emotions, parts, schemas, and daily ratings. Attributes: `label`, `field`, `max`, `type`, `small`, `info` (makes the label tappable → `row-info` event)
- **`<urge-row>`**: 0–5 pills plus an "acted on it?" no/yes that appears once the row is engaged. Attributes: `label`, `field` (urge rating), `action` (acted boolean). Dispatches `field-change` for each separately.
- **`<toggle-row>`**: Tri-state no/yes pills (`null` = unanswered, `false`, `true`). Tapping the selected pill clears it. Unanswered toggles are omitted from the share view. Used for actions and daily toggle categories. Attributes: `label`, `field`
- **`<skill-row>`**: 4 text pills (aware/tried/used/auto) + "helped" toggle. Used for DBT skills. Attributes: `label`, `field`

All of them dispatch `field-change` CustomEvents (bubbles, composed) caught by a single centralized listener in `initStaticHandlers()`. State is pushed down via the `.value` property setter.

Attach event listeners once in `connectedCallback()` after `_render()` — never in `_render()` itself.

## Data Model

- **Emotions**: User-defined list in `prefs.emotions` (seeded from `DEFAULT_EMOTIONS`, 20 names). Stored as `emotion_<index>` (0–5). Displayed in `emotionDisplayOrder()`: by `EMOTION_FAMILY`, most pleasant first, never labelled as positive/negative. New defaults are appended to existing vaults and hidden.
- **Parts**: User-defined list in `prefs.parts` (IFS). Stored as `part_<index>` (0–5). Section hidden until a part exists; parts are added in the dialog's Parts tab or on the card.
- **Schemas & modes**: Fixed vocabulary `SCHEMAS` (28: Young's 18 schemas + 10 modes), grouped by `SCHEMA_GROUPS`. Stored as `schema_<index>` (0–5). All hidden by default.
- **Urges**: Fixed vocabulary `URGES` of `{ label, action }` (21). Rating stored as `urge_<index>` (0–5); whether the user acted stored as the boolean named by `action` (legacy ids from the old Actions section, e.g. `selfHarmed`). `URGE_GROUPS` orders the card and chooser.
- **Skills**: Fixed vocabulary in `SKILLS` array of `{ label, desc, similar }` objects (95 items: DBT 0–30, ACT 31–44, CBT 45–57, IFS 58–67, Schema 68–76, CAMS 77–83, CFT 84–88, Somatic 89–94). Stored as `skill_N`. Value encodes engagement × 2 + helped (0–7). `SKILL_CATALOG` is the browsable tree (school → groups → indices) used by the chooser, the daily-card headers, and the share view; `SKILL_META` is the index → school/group back-reference. `similar` links are cross-school and made symmetric at load; they surface only in the info popover, never inside a school's tab. Prefs carry `knownSkillCount` so skills appended later start hidden for existing vaults.
- **Daily / Basics**: `CATEGORIES` entries carry `section: 'daily'` (state: sleep, energy, pain, overall day, therapy session, cycle, caffeine) or `'basics'` (practice: exercise, meals, meds, water, sunlight...). `type` is `complex` (hand-built HTML), `toggle` (null/false/true) or `rating` (0–5). One hidden list, `prefs.hiddenCategories`. Basics render as the first group under Skills.
- **Toggles** are tri-state: `null` = unanswered (omitted from share view), `false`, `true`.

## Share Links

Two formats coexist:

- **`#share=PAYLOAD`**: Self-contained. Encrypted payload encoded directly in the URL fragment. Works forever, no server dependency. Can be very long (2K–30K+ chars).
- **`#relay=TOKEN`**: Short link (5-char token). App fetches the encrypted payload from `/api/relay/TOKEN`. Expires after a user-chosen TTL (1 day to 3 months, default 30 days). The vault remembers its live link in `prefs.activeShare = { token, editKey, passphrase, expiresAt }` (inside the encrypted prefs) so the next share can update the same link in place via PUT; the share-setup dialog offers "Update the existing link" vs "Make a new link", with the passphrase prefilled and changeable. Changing the TTL in the result dialog also updates in place rather than minting a new token.

Entries between checkpoint and today are serialized to JSON, DEFLATE-compressed, AES-GCM encrypted with a share passphrase, and base64url-encoded.

Share payload format (v3): `{ entries, hidden, emotions, parts }` — the vault's emotion and part name lists travel with the payload so indices resolve in the viewer. v2 (`{ entries, hidden }`) and v1 (flat entries) are still parsed; emotions then map through the first 13 `DEFAULT_EMOTIONS`.

## Relay Service

`relay/app.py` — FastAPI + SQLite. Stores encrypted payloads temporarily.

**Token scheme**: 26 letter prefixes (a–z), each active for 1 week, cycling every 26 weeks. Token = prefix + 4 random alphanumeric chars. When a prefix cycles back, all its old tokens are guaranteed expired. Cleanup runs on each POST.

**Endpoints**:
- `POST /api/relay` — store payload, return token + `edit_key` + expiry. Only the key's SHA-256 is stored.
- `PUT /api/relay/{token}` — replace the payload in place and restart the TTL; requires the `edit_key` (403 otherwise, 404 if expired/unknown). Links created before edit keys existed can't be updated, only replaced.
- `GET /api/relay/{token}` — retrieve payload or 404 if expired
- `GET /api/relay/health` — status check

## Key Functions

- `buildDynamicSections()`: Creates web component elements for schemas/urges/daily/basics/skills based on vocabulary arrays minus hidden items
- `renderCustomLists()`: Builds emotion and part rows (rating-row inside .emotion-row wrappers with 7-day avg + hide button) via `CUSTOM_LISTS`
- `openWizard(mode)`: The field-visibility dialog. `firstRun`/`newUser` walk through steps with Next/Back/Skip and a summary; `edit` (pencil button in the header, the only entry point) shows Cancel/Done, and Done renders a +/− review of the draft vs. saved prefs (`wizardDiff()`) before Save. Section tabs in the header are clickable in every mode.
- `renderWizardSkills()`: Tabbed skills chooser (one tab per school in `SKILL_CATALOG`)
- `showInfoCard(kicker, title, desc, similar)`: The info popover; `showSkillInfo(idx)` / `showSchemaInfo(idx)` wrap it. Triggered by `row-info` events (tapping a skill-row or `info` rating-row label) or the ? buttons in the chooser
- `renderEntry()`: Pushes current date's entry values into all web components and static inputs
- Prefs carry `knownSkillCount`, `knownUrgeCount`, `knownSchemaCount`, `knownCategories` so vocabulary appended after a vault's last save starts hidden there
- `renderShareDayCard()`: Generates HTML string for one day's read-only share view
- `initStaticHandlers()`: Attaches event listeners once — includes the centralized `field-change` handler
- `setupShareUnlock()`: Configures the share passphrase form for both `#share=` and `#relay=` flows

## Working style

This is a personal therapeutic tool. Treat it accordingly: small focused changes over sweeping rewrites, careful when touching anything that could affect stored entries or share URLs, no telemetry of any kind, no third-party dependencies in the frontend. The encryption is what makes the project meaningful — never weaken it, never log decrypted content, never bypass passphrase prompts.
