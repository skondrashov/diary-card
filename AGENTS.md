# dbt.thisminute.org

Encrypted DBT (Dialectical Behavior Therapy) diary card. Single static HTML file, no backend, no build step.

## Architecture

- **Single file**: `index.html` contains all CSS, HTML, and JS (~3750 lines)
- **JS structure**: Web component definitions at top (outside IIFE), then one large IIFE containing all app logic
- **Encryption**: AES-GCM via Web Crypto API. Multi-vault support — each vault is an isolated diary with its own passphrase
- **Storage**: localStorage only. Entries keyed by date (`YYYY-MM-DD`), encrypted per-vault
- **Theming**: CSS custom properties on `:root` (dark default) with `body.light-mode` overrides

## Web Components

Three custom elements with Shadow DOM, defined before the IIFE:

- **`<rating-row>`**: Numeric pill selector (0–N). Used for emotions and urges. Attributes: `label`, `field`, `max`, `type`, `small`
- **`<toggle-row>`**: On/off switch. Used for actions and daily toggle categories. Attributes: `label`, `field`
- **`<skill-row>`**: 4 text pills (aware/tried/used/auto) + "helped" toggle. Used for DBT skills. Attributes: `label`, `field`

All three dispatch `field-change` CustomEvents (bubbles, composed) caught by a single centralized listener in `initStaticHandlers()`. State is pushed down via the `.value` property setter.

Event listeners attach once in `connectedCallback()` after `_render()` — never in `_render()` itself.

## Data Model

- **Emotions**: User-defined list in `prefs.emotions`. Stored as `emotion_0`, `emotion_1`, etc. (0–5 intensity)
- **Urges**: Fixed vocabulary in `URGES` array. Stored as `urge_0`, `urge_1`, etc. (0–5 intensity)
- **Actions**: Fixed vocabulary in `ACTIONS` array. Stored by action ID string (boolean)
- **Skills**: Fixed vocabulary in `SKILLS` array (26 items). Stored as `skill_0`–`skill_25`. Value encodes engagement × 2 + helped (0–7)
- **Daily**: Sleep (hours + quality), exercise (mins + type), meals (string array), toggle categories (boolean)

## Share Links

Entries between checkpoint and today are serialized to JSON, DEFLATE-compressed, AES-GCM encrypted with a share passphrase, and base64url-encoded into a URL fragment (`#share=...`).

**Critical constraint**: `URGES`, `ACTIONS`, and `SKILLS` arrays are append-only. Their indices are baked into stored entries and share URLs. Never reorder or remove items — only append.

Share payload format (v2): `{ entries: {...}, hidden: {...} }` when items are hidden, or flat entries object for backward compat when nothing is hidden.

The URL budget indicator tracks share link size in real time using a fast estimation path that avoids PBKDF2.

## Key Functions

- `buildDynamicSections()`: Creates web component elements for urges/actions/skills/toggle-categories based on vocabulary arrays minus hidden items
- `renderEmotions()`: Builds emotion rows (rating-row inside .emotion-row wrappers with 7-day avg + hide button)
- `renderEntry()`: Pushes current date's entry values into all web components and static inputs
- `renderShareDayCard()`: Generates HTML string for one day's read-only share view
- `initStaticHandlers()`: Attaches event listeners once — includes the centralized `field-change` handler

## Testing

No local dev server or test suite. Verify changes via static analysis (grep for stale refs, check selectors match) and manual testing in production. Open `index.html` directly in a browser via `start index.html`.

## Deployment

Managed through a separate ops pipeline. Do not push or deploy directly.
