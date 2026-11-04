# dbt.thisminute.org

A DBT (Dialectical Behavior Therapy) diary card that runs entirely in your browser. All data is encrypted on your device with AES-256-GCM before it touches localStorage. There is no account, no backend database, and no way for anyone (including the site operator) to read your entries without your passphrase.

Live at [dbt.thisminute.org](https://dbt.thisminute.org).

## What it tracks

- Emotions (user-defined, 0-5 intensity, with 7-day rolling averages)
- Urges (0-5 intensity)
- Actions (yes/no)
- Skills used (engagement level + whether it helped), chosen from a catalog spanning DBT, ACT, CBT, IFS, schema therapy, CAMS, CFT and somatic approaches
- Sleep, exercise, meals, notes
- Custom toggle categories

All fields are configurable. An onboarding wizard walks new users through hiding the ones they don't need.

## Sharing with a therapist

You can share a range of entries (from a checkpoint date to today) as an encrypted link. The recipient enters a share passphrase you give them separately to decrypt and view the entries in a read-only calendar/list view.

Short links go through a relay service that stores the encrypted payload temporarily (1 day to 3 months, your choice) and then deletes it. The relay cannot read the entries. A permanent full-length link is also available that works without any server.

## Privacy model

- Encryption: AES-256-GCM, key derived via PBKDF2 with 200,000 iterations and a random salt
- Storage: browser localStorage only, encrypted per-vault
- Network: no requests are made except when sharing (relay stores an opaque encrypted blob temporarily)
- No cookies, no analytics, no tracking
- Multiple vaults supported, each with its own passphrase
- If you forget your passphrase, that diary is unrecoverable. There is no reset mechanism.

## Running locally

Open `index.html` in a browser. That's it. No build step, no dependencies, no server required for basic use.

The share relay (`relay/`) is a small FastAPI service needed only for short share links. See `relay/requirements.txt` for dependencies.

## Structure

```
index.html              The entire app (HTML + CSS + JS, single file)
relay/app.py            Share link relay service (FastAPI + SQLite)
relay/requirements.txt  Python dependencies for the relay
deploy/                 Systemd service file for the relay
```

## License

MIT
