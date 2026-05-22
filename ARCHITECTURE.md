# Architecture — AI Insight Digest

## 1. Overview

AI Insight Digest is an asynchronous Telegram bot built on a clean, layered
architecture. Every external interaction (HTTP, database, Telegram, Gemini) is
non-blocking; the whole application runs in a single asyncio event loop that
hosts both the aiogram polling loop and the APScheduler job runner.

```
┌──────────────────────────────────────────────────────────────────┐
│                         asyncio event loop                        │
│                                                                    │
│   ┌─────────────────┐                  ┌──────────────────────┐    │
│   │ aiogram polling │                  │ APScheduler jobs     │    │
│   │  (bot handlers) │                  │  ingest / score /    │    │
│   │                 │                  │  deliver             │    │
│   └────────┬────────┘                  └──────────┬───────────┘    │
│            │                                      │                │
│            └──────────────┬───────────────────────┘                │
│                           ▼                                        │
│                    service layer                                   │
│         (ingestion · scoring · digest · delivery)                   │
│                           │                                        │
│            ┌──────────────┼──────────────┐                         │
│            ▼              ▼              ▼                          │
│       collectors      Gemini API     repositories ──► PostgreSQL    │
└──────────────────────────────────────────────────────────────────┘
```

## 2. Layers

| Layer | Package | Responsibility | Depends on |
|---|---|---|---|
| Configuration | `app.config` | Validated settings singleton | — |
| Domain | `app.domain` | Enums, DTOs, the Gemini schema | — |
| Persistence | `app.db` | Engine, ORM models, repositories | domain |
| Collectors | `app.collectors` | Source adapters → `RawItem` | domain |
| AI | `app.ai` | Gemini client + prompts | domain |
| Services | `app.services` | Pipeline orchestration | all of the above |
| Bot | `app.bot` | aiogram handlers, keyboards, middleware | services |
| Scheduler | `app.scheduler` | APScheduler jobs | services, bot |
| Entrypoints | `app.__main__`, `app.cli` | Process wiring | everything |

Dependencies point strictly downward. The domain layer is framework-agnostic
and importable anywhere; nothing reads `os.environ` except `app.config`.

## 3. The pipeline

The pipeline mirrors the four stages of the technical specification.

### Stage 1–2 — Ingestion (`services/ingestion.py`)

Runs every `INGEST_INTERVAL_HOURS`.

1. **Collect.** All collectors run concurrently (`asyncio.gather`). Each is
   isolated by `Collector.safe_collect` — a failing source returns `[]`, never
   aborts the cycle.
2. **Deduplicate.**
   - *Layer 1 — URL identity:* URLs are normalised (scheme, `www`, tracking
     params, fragments stripped) and matched against a `UNIQUE` index.
   - *Layer 2 — title similarity:* `rapidfuzz.token_set_ratio` against the
     recent window catches the same story from different sources; the
     duplicate's URL is merged into the canonical item's `extra_sources`.
3. Survivors are persisted with status `RAW`.

**Sources (tiered by signal quality):**

| Tier | Collector | Anti-hype gate |
|---|---|---|
| 1 | RSS (OpenAI, DeepMind, HF, Meta AI, …) | trusted first-party |
| 1 | Hugging Face Daily Papers | upvote-ranked research |
| 2 | Hacker News (Algolia API) | `points ≥ HN_MIN_SCORE` |
| 2 | Reddit (`r/LocalLLaMA`, `r/MachineLearning`) | per-subreddit score floor |
| 3 | GitHub Trending | AI-keyword relevance filter |
| 3 | Product Hunt *(optional)* | AI-topic filter |

### Stage 3 — Scoring (`services/scoring.py`)

Runs daily, two hours before the default digest time.

Each `RAW` item is sent to **Gemini** (`gemini-2.5-flash`) with a Pydantic
`response_schema` (`GeminiVerdict`), guaranteeing a typed result. Concurrency
is bounded by a semaphore; transient failures are retried with exponential
backoff (`tenacity`).

The verdict drives a status transition:

```
score < THRESHOLD     → REJECTED
THRESHOLD ≤ score ≤ 8 → APPROVED   (scheduled digest)
score > 8             → BREAKING   (urgent push outside the schedule)
```

### Moderation (`bot/handlers/moderation.py`)

The legacy moderation router is still present for manual operator workflows,
but the main news pipeline is now fully automatic: scheduled items no longer
wait for approval.

### Stage 4 — Digest & delivery (`services/digest.py`, `delivery.py`)

- **Urgent push (4a).** Items in `BREAKING` are broadcast as single-news alerts
  outside the schedule. Day/time restrictions are bypassed; a chat-level pause
  is still respected.
- **Scheduled digest (4b).** `build_digest` selects the top approved items of
  the last `LOOKBACK_DAYS`, renders a MarkdownV2 post, and marks only the
  delivered items `POSTED`.
- **Deliver (4c).** A one-minute scheduler tick first flushes urgent items,
  then finds chats whose local weekday and local time match their
  `digest_days` + `digest_times` settings and broadcasts the digest via the
  rate-limited `Broadcaster`.

## 4. Data model

```
groups ──1:N── delivery_log

news_items   (the pool: RAW → {APPROVED|BREAKING|REJECTED} → POSTED)
```

| Table | Purpose | Key columns |
|---|---|---|
| `groups` | Subscribed chats | `id` (chat id), `digest_times`, `digest_days`, `timezone`, `last_digest_on`, `digest_paused`, `is_active` |
| `news_items` | The news pool | `normalized_url` (UNIQUE), `status`, `score`, `summary_ru`, `utility_ru`, `category`, `extra_sources` |
| `delivery_log` | Delivery audit trail | `group_id`, `digest_date`, `status`, `error` |

Schema is managed by **Alembic**; the engine is async (`asyncpg`), with
JSON columns stored as `JSONB` on PostgreSQL and plain `JSON` on SQLite (tests).

## 5. Cross-cutting concerns

- **Async everywhere.** httpx, SQLAlchemy async, aiogram, the Gemini `aio`
  client. Sync-only `feedparser` is dispatched via `asyncio.to_thread`.
- **Transactions.** `session_scope()` (services) and `DbSessionMiddleware`
  (bot) both commit on success and roll back on any exception.
- **Resilience.** Collector failures, Gemini failures and per-chat send
  failures are all isolated — the surrounding batch always completes.
- **Telegram limits.** `Broadcaster` paces below 30 msg/s and obeys
  `TelegramRetryAfter`; `TelegramForbiddenError` deactivates the chat.
- **Observability.** `structlog` emits JSON logs in production; stdlib loggers
  (aiogram, SQLAlchemy, APScheduler) are routed through the same pipeline.
- **Health.** The delivery tick writes a heartbeat file; the Docker
  `HEALTHCHECK` (`python -m app.health`) verifies its freshness.

## 6. Extending the system

- **A new source:** subclass `Collector`, implement `collect`, register it in
  `collectors/registry.py`. Nothing else changes.
- **Editorial policy:** the scoring rubric lives entirely in
  `ai/prompts.py::SCORING_SYSTEM_PROMPT`.
- **A new command:** add a handler to a router in `bot/handlers/`.
