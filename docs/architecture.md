# Architecture

## Why this folder layout

The project is organized as a small **layered/hexagonal** system: each layer only
knows about the layer directly below it, and the boundaries map to concrete
SOLID responsibilities. That's deliberate — it's the same shape you'd want in
a real internal QA tool, and it's the shape that makes the project easy to
extend without touching unrelated code.

```
app/
├── config/       # Single source of truth for settings (env vars, paths, model names)
├── utilities/    # Cross-cutting concerns with no business logic (logging today)
├── playwright/   # Pytest hooks/fixtures that hang off the Playwright test run
├── collectors/   # One class per artifact type: screenshot, video, trace, logs, ...
├── analyzers/    # Combines collector output into one FailureBundle + rule-based classification
├── llm/          # Pluggable AI provider interface, prompts, and JSON schema contracts
├── database/     # SQLAlchemy models + repository (persistence, nothing else)
├── reports/      # Links pytest-html / Allure / AI report artifacts together
└── dashboard/    # Streamlit UI — reads the database, never calls the LLM on its own
```

### Why each folder exists

- **`config/`** — Every other module asks `get_settings()` for configuration
  instead of calling `os.getenv` inline. That's the Dependency Inversion
  Principle: modules depend on an abstraction (`Settings`), not on the
  environment directly, so tests can construct a `Settings` object by hand
  without touching real env vars.

- **`utilities/`** — Things every layer needs (structured logging today, small
  helpers later) but that carry no domain knowledge. Kept separate so
  `collectors/` and `llm/` don't accidentally depend on each other just to
  share a logger.

- **`playwright/`** — This is the *only* place that touches `pytest`/Playwright
  hook APIs (`pytest_runtest_makereport`, fixtures, etc.). Isolating hook code
  here means the collection logic in `collectors/` can be unit-tested without
  spinning up a real Playwright browser.

- **`collectors/`** — Single Responsibility Principle, applied literally: one
  class per artifact (screenshot, video, trace, console logs, network logs,
  stack trace, environment info). Each collector knows how to gather exactly
  one thing and nothing else. Adding a new artifact type later (say, HAR
  files) means adding one class, not editing an existing one — Open/Closed.

- **`analyzers/`** — Sits above `collectors/`: assembles their output into a
  single `FailureBundle`, and applies cheap, deterministic, non-AI
  classification (e.g. "TimeoutError in message" → category `Timeout`) so the
  dashboard has a useful category *before* anyone spends an API token.

- **`llm/`** — The pluggable AI boundary. `base_provider.py` defines the
  interface; `openai_provider.py` and `claude_provider.py` implement it;
  `provider_factory.py` picks one based on `Settings.llm_provider`. Swapping
  or adding a provider never touches calling code (Open/Closed + Liskov: any
  provider can stand in for the base class). `prompts.py` and `schemas.py`
  keep prompt text and the expected JSON contract in one auditable place.

- **`database/`** — SQLAlchemy models plus a thin repository layer. Nothing
  outside `database/` writes raw SQL or holds a `Session` open — callers go
  through repository methods. That keeps persistence swappable (SQLite today,
  Postgres later) without touching the dashboard or analyzers.

- **`reports/`** — Doesn't generate pytest-html or Allure output itself
  (pytest and the Allure CLI do that); it links the resulting report paths
  back into the database so the dashboard can deep-link to them.

- **`dashboard/`** — Streamlit only *reads*: it queries the database and
  renders. The one exception is the explicit "Analyze Failure" button, which
  is the single, deliberate place in the whole UI that can spend an API
  token — and only on click.

- **`tests/`** — Sample Playwright + pytest tests, some intentionally
  written to fail, used to generate real failure artifacts to demo the
  pipeline end-to-end.

- **`data/`** — Local SQLite database and collected artifacts. Fully
  git-ignored; this is generated state, not source.

## Data flow

```
pytest run (Playwright test fails)
        │
        ▼
app/playwright hooks fire on failure
        │
        ▼
app/collectors gather screenshot, video, trace, console logs,
network logs, stack trace, environment info
        │
        ▼
app/analyzers builds a FailureBundle + rule-based category guess
        │
        ▼
app/database persists the run + failure + artifact paths (no AI yet)
        │
        ▼
   [ user opens dashboard, browses failures for free ]
        │
        ▼
   user clicks "Analyze Failure"  ──────────────► app/llm calls the
                                                   configured provider
        │
        ▼
Structured JSON report validated against app/llm/schemas.py
        │
        ▼
app/database stores the AI report, linked to the failure
        │
        ▼
app/dashboard renders the AI report card
```

The AI step is drawn off to the side on purpose: everything above the "user
clicks" line runs automatically and free of charge every test run; nothing
below it runs without an explicit click.

## Database schema

Three tables (`app/database/models.py`), one clear responsibility each:

- **`TestRun`** — one row per pytest session: `execution_id`, timing, pass/fail/
  skip counts, OS/browser, git branch + commit.
- **`TestResult`** — one row per test within a run: name, status, duration,
  error message, stack trace, every artifact path, and a `rule_based_category`
  — a cheap, deterministic, non-AI classification available for every failure
  at zero API cost (see `app/analyzers/category_classifier.py` in Phase 3).
- **`AIAnalysis`** — one row per AI analysis *invocation*, many-to-one against
  `TestResult` rather than a flat set of nullable columns bolted onto it.

That last choice is the one worth defending in an interview: LLM output isn't
deterministic, and letting a user re-run "Analyze Failure" for a second
opinion should keep history, not silently overwrite the first attempt. The
trade-off is one more join to get "the" analysis for a failure — solved with
`TestResult.latest_ai_analysis` / `Repository.get_latest_ai_analysis()` so
callers don't need to know the history exists.

`Repository` (`app/database/repository.py`) takes a `Session` through its
constructor instead of importing a global engine. That's dependency
inversion applied concretely: `tests/test_database.py` points the same
`Repository` class at an in-memory SQLite engine with zero mocking, so the
tests exercise real SQL, real constraints, and real aggregate queries.
