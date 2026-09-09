# 🤖 AI Insight Digest

A Telegram bot that **collects, semantically scores and broadcasts a
twice-weekly digest of the most significant AI/ML news** — and ruthlessly
filters out the hype.

Round the clock it pulls from first-party vendor blogs, the AI tech press
(TechCrunch, VentureBeat, MIT Technology Review …), Hacker News, Hugging
Face and GitHub Trending, and hands each candidate to **Google Gemini** for a
1–10 significance score. Twice a week — **Monday and Friday morning** — every
subscribed chat gets a clean, scannable digest of the best of the period, and
nothing in between.

```
collect → deduplicate → score (Gemini) → scheduled digest → broadcast
```

---

## Why it is good

| Capability | What it does |
|---|---|
| **Tiered sources** | Vendor blogs + AI tech press (tier 1) → HN/Hugging Face (tier 2) → GitHub/Product Hunt (tier 3), each with its own anti-hype gate. |
| **Two-layer dedup** | Exact normalised-URL match **and** fuzzy title matching — the same release reported by three sources collapses into one item with merged links. |
| **Structured AI scoring** | Gemini is called with a Pydantic `response_schema`, so the result is always a typed verdict — never unparseable free text. |
| **Automatic editorial routing** | Score `< 7` is rejected; everything above it is queued for the next scheduled digest, best items first. |
| **Quiet by default** | Two deliveries a week, Monday and Friday morning. Out-of-schedule urgent pushes exist but ship disabled (`BREAKING_ENABLED`). |
| **Per-chat scheduling** | Any chat can override the default weekdays, delivery times and timezone; the digest is built fresh for every due slot. |
| **Rate-limit aware** | Broadcasting paces itself under Telegram's 30 msg/s ceiling and honours `RetryAfter`. |
| **Production-ready** | Async end-to-end, structured JSON logs, Alembic migrations, Docker/Compose, healthcheck, CI, full test suite. |

---

## Quick start

### 1. Configure

```bash
cp .env.example .env
# edit .env — set BOT_TOKEN, GEMINI_API_KEY, ADMIN_IDS
```

### 2. Run with Docker (recommended)

```bash
make docker-up      # postgres + migrations + bot
make docker-logs    # follow the logs
```

### 3. Or run locally

```bash
make install        # venv + dependencies
make migrate        # apply database schema
make run            # start the bot
```

Then add the bot to any Telegram group — it registers automatically and starts
delivering the digest on Monday and Friday mornings.

---

## Deploy to Railway

The repository is Railway-ready ([`railway.json`](railway.json) builds from the
`Dockerfile` and runs migrations on every deploy).

1. **New Project → Deploy from GitHub repo** → pick this repository.
2. **Add a database:** *New → Database → PostgreSQL*. Then expose that
   database URL to the bot service as `DATABASE_URL` (for example with a
   Railway variable reference to the Postgres service's connection URL). The
   app rewrites plain Postgres URLs to the async driver, so no manual driver
   editing is needed.
3. **Set variables** on the bot service (*Variables* tab):
   `BOT_TOKEN`, `GEMINI_API_KEY`, `ADMIN_IDS`, and optionally `DIGEST_TIME`,
   `DIGEST_DAYS`, `TIMEZONE`, `SCORING_BUDGET`, … (see
   [`.env.example`](.env.example)).
4. **Deploy.** On each deploy Railway runs `alembic upgrade head` and then the
   bot — see `startCommand` in `railway.json`.

The bot is a long-running worker (Telegram long-polling) — no public port or
domain is required.

---

## Commands

**In a group (chat administrators):**

| Command | Action |
|---|---|
| `/digest_now` | Send the current digest immediately |
| `/digest_time HH:MM [HH:MM ...]` | Set one or more daily delivery times |
| `/digest_days пн ср пт` | Set which weekdays scheduled news may be sent |
| `/timezone Europe/Moscow` | Set this chat's timezone |
| `/status` | Show this chat's settings |
| `/help` | Usage help |

**In a private chat (bot operators — `ADMIN_IDS`):**

| Command | Action |
|---|---|
| `/stats` | Pool and subscriber statistics |
| `/run_ingest` | Trigger a collection cycle now |
| `/run_scoring` | Trigger a Gemini scoring cycle now |
| `/pending` | Re-send all moderation cards |

---

## Operational CLI

Run individual pipeline stages without the scheduler:

```bash
make ingest    # python -m app.cli ingest
make score     # python -m app.cli score
make digest    # python -m app.cli digest   (build + broadcast now)
```

---

## Development

```bash
make check     # ruff + mypy + pytest
make test      # tests with coverage
make fmt       # auto-format and fix
```

CI (GitHub Actions) runs lint, format check, type-check and the test suite on
every push.

---

## Configuration reference

All settings come from environment variables / `.env` — see
[`.env.example`](.env.example) for the annotated list. Highlights:

| Variable | Default | Meaning |
|---|---|---|
| `SCORE_THRESHOLD` | `7` | Minimum Gemini score to reach a digest |
| `DIGEST_SIZE` | `5` | Items per digest |
| `DIGEST_TIME` / `DIGEST_DAYS` | `09:00` / `1,5` | Default delivery slot and weekdays (Mon + Fri) |
| `TIMEZONE` | `Europe/Moscow` | Timezone new chats are scheduled in |
| `BREAKING_ENABLED` | `false` | Push 9–10 scored news outside the schedule |
| `INGEST_INTERVAL_HOURS` | `3` | Collection frequency |
| `HN_MIN_SCORE` | `100` | Hacker News points floor (anti-hype) |

---

## Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — full system design, data flow and schema.

## License

MIT.
