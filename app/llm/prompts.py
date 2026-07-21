"""Prompt construction. Kept entirely separate from the providers so the
prompt text is one auditable, diffable place — not buried inside an API call.

Design choices worth explaining, since each one directly targets a named
requirement (structured JSON, no hallucinations, actionable fixes):

- The rule-based category is included but explicitly labeled "heuristic, not
  authoritative." Without that framing, models tend to rubber-stamp
  whatever category they're shown rather than reasoning from the actual
  stack trace/logs — which defeats the point of asking a second, more
  capable opinion.
- Empty sections (no console log, no network log, no test source found) are
  omitted rather than included as "(none)" placeholders. Fewer irrelevant
  tokens means less surface area for the model to hallucinate a connection
  that isn't there, and lowers cost.
- The system prompt explicitly tells the model to lower its own
  confidence_score rather than guess when evidence is thin, and to prefer a
  concrete, actionable suggested_fix over a vague one — both are otherwise
  common LLM failure modes for this kind of task.
- Documentation links are requested "only if you are confident they exist"
  (also enforced by the schema's field description) — LLMs invent plausible
  looking URLs readily, and a fabricated link is worse than no link.
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM_PROMPT = """\
You are a senior Test Automation Engineer (SDET) with deep Playwright and web \
application debugging expertise, helping a teammate triage one failed automated test.

Ground rules:
- Base your analysis ONLY on the evidence given below. Never invent file names, line \
numbers, API names, or application behaviour you have not been shown.
- If the evidence is insufficient to be confident, say so by lowering confidence_score — \
do not guess with false confidence.
- Prefer the most specific applicable failure_category. Use "Unknown" only if nothing \
else genuinely fits.
- suggested_fix must be something a human could act on today: a concrete code change, \
wait strategy, or specific next investigation step — not "check the test" or "investigate further".
- Only include a documentation URL if you are confident it is a real, official Playwright \
documentation page. If unsure, omit relevant_documentation entirely.
- Respond by calling the function/tool you are given with a single JSON object matching \
its schema exactly. Do not include commentary outside of it.
"""


@dataclass
class AnalysisContext:
    test_name: str
    status: str
    duration_seconds: float
    error_message: str
    stack_trace: str
    rule_based_category: str | None = None
    console_log: str | None = None
    network_log: str | None = None
    environment: dict[str, str] | None = None
    test_source: str | None = None


def build_user_prompt(ctx: AnalysisContext) -> str:
    sections = [
        f"## Test\n{ctx.test_name}",
        f"Status: {ctx.status} | Duration: {ctx.duration_seconds:.2f}s",
    ]

    if ctx.rule_based_category:
        sections.append(f"## Rule-based category (heuristic, not authoritative)\n{ctx.rule_based_category}")

    sections.append(f"## Error message\n{ctx.error_message or '(none captured)'}")
    sections.append(f"## Stack trace\n```\n{ctx.stack_trace or '(none captured)'}\n```")

    if ctx.test_source:
        sections.append(f"## Test source code\n```python\n{ctx.test_source}\n```")
    if ctx.console_log:
        sections.append(f"## Browser console log\n```\n{ctx.console_log}\n```")
    if ctx.network_log:
        sections.append(f"## Failed network requests\n```\n{ctx.network_log}\n```")
    if ctx.environment:
        env_lines = "\n".join(f"- {key}: {value}" for key, value in ctx.environment.items())
        sections.append(f"## Environment\n{env_lines}")

    return "\n\n".join(sections)
