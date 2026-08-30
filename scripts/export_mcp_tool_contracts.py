#!/usr/bin/env python3
"""Export registered UniVA MCP tool signatures without importing runtime dependencies.

This is a maintenance helper for keeping skills/core Tool Contract sections in
sync with @mcp.tool functions. It parses source files with ast and prints JSON.
It intentionally does not import univa.mcp_tools modules, so it will not start
models, load config, or require provider dependencies.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT / "univa" / "mcp_tools"


def _annotation(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _default(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        try:
            return ast.unparse(node)
        except Exception:
            return "<expr>"


def _is_mcp_tool(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in fn.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "tool":
            value = target.value
            if isinstance(value, ast.Name) and value.id == "mcp":
                return True
    return False


def _parameters(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    args = list(fn.args.posonlyargs) + list(fn.args.args)
    defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
    params: list[dict[str, Any]] = []
    for arg, default_node in zip(args, defaults):
        params.append(
            {
                "name": arg.arg,
                "annotation": _annotation(arg.annotation),
                "required": default_node is None,
                "default": _default(default_node) if default_node is not None else None,
            }
        )
    if fn.args.vararg:
        params.append({"name": "*" + fn.args.vararg.arg, "annotation": _annotation(fn.args.vararg.annotation), "required": False, "default": None})
    for arg, default_node in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
        params.append(
            {
                "name": arg.arg,
                "annotation": _annotation(arg.annotation),
                "required": default_node is None,
                "default": _default(default_node) if default_node is not None else None,
            }
        )
    if fn.args.kwarg:
        params.append({"name": "**" + fn.args.kwarg.arg, "annotation": _annotation(fn.args.kwarg.annotation), "required": False, "default": None})
    return params


def main() -> int:
    tools: list[dict[str, Any]] = []
    for source in sorted(MCP_DIR.glob("*.py")):
        if source.name == "base.py":
            continue
        tree = ast.parse(source.read_text(), filename=str(source))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_mcp_tool(node):
                tools.append(
                    {
                        "tool": node.name,
                        "module": str(source.relative_to(ROOT)),
                        "async": isinstance(node, ast.AsyncFunctionDef),
                        "parameters": _parameters(node),
                        "return_annotation": _annotation(node.returns),
                        "docstring_summary": (ast.get_docstring(node) or "").strip().splitlines()[0] if ast.get_docstring(node) else "",
                    }
                )
    print(json.dumps({"tool_count": len(tools), "tools": tools}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
