# AI Test Failure Analyzer for Playwright

> Status: work in progress — built incrementally, phase by phase. This README
> will be expanded into the full project documentation in a later phase; for
> now see [`docs/architecture.md`](docs/architecture.md) for the design.

**No API requests are made unless the user explicitly initiates AI analysis**
(via the dashboard's "Analyze Failure" button or `python analyze_failure.py`).
Everything else — running tests, collecting artifacts, browsing the
dashboard — works fully offline.
