# Enabling AI analysis in CI (optional, opt-in)

The main CI workflow (`.github/workflows/ci.yml`) never runs AI analysis and
never references an API key secret — every push and pull request only runs
tests and generates the pytest-html/Allure reports, exactly like it would
with no AI feature in the project at all.

A second, separate workflow — `.github/workflows/ai-analysis-manual.yml` —
exists for teams that *do* want CI-triggered analysis, but it is designed so
that committing it, by itself, spends nothing:

- Its only trigger is `workflow_dispatch` — GitHub never fires this
  automatically; it only runs when someone with write access clicks **Run
  workflow** in the Actions tab (or calls the dispatch API themselves).
- Even then, it calls `analyze_failure.py` exactly as documented for local
  use, which fails with a friendly message and makes no request if no key is
  configured (see `app/llm/provider_factory.py`).

## To enable it

1. Choose a provider and get an API key (OpenAI or Anthropic).
2. In the repository: **Settings → Secrets and variables → Actions → New
   repository secret**. Add `OPENAI_API_KEY` or `CLAUDE_API_KEY` (matching
   whichever provider you'll use).
3. Optionally add a repository **variable** (not secret) named `LLM_PROVIDER`
   set to `openai` or `claude` — it defaults to `openai` if omitted.
4. Go to the **Actions** tab → **AI Analysis (manual)** → **Run workflow**.
   Leave the `failure_id` input blank to analyze the most recent failure, or
   supply a specific id.

## Why this is a second workflow, not a flag on the main one

A boolean input on the main workflow (`run_ai: true/false`) would still mean
every push *could* trigger a paid API call depending on how someone invokes
it, and a single YAML file mixing "always run" and "run only if asked"
concerns is harder to audit at a glance. Keeping AI analysis in a workflow
that categorically cannot trigger on push/PR — only on an explicit human
action — makes the "no request without explicit action" guarantee something
you can verify by reading the trigger, not by reading every branch of the
logic.
