"""Extracts just the failing test *function's* source, not the whole file.

Feeding the LLM the entire test file wastes tokens on unrelated tests and
gives it more surface area to latch onto code that has nothing to do with
the failure. Using `ast` to slice out exactly the matching function is more
precise than any truncation heuristic and doesn't depend on the file being
small.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def _base_test_name(test_name: str) -> str:
    """ "tests/ui/test_x.py::test_login[chromium]" -> "test_login" """
    function_part = test_name.split("::")[-1]
    return re.sub(r"\[.*\]$", "", function_part)


def find_test_source(test_file: str | None, test_name: str) -> str | None:
    if not test_file:
        return None

    path = Path(test_file)
    if not path.is_file():
        return None

    function_name = _base_test_name(test_name)

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node)

    return None
