from __future__ import annotations

from dataclasses import dataclass

import libcst as cst
from libcst import FlattenSentinel


@dataclass(frozen=True)
class CstPatchResult:
    changed: bool
    reason: str
    updated_source: str | None = None


class _ExpectVisibleInserter(cst.CSTTransformer):
    def __init__(self, *, selector_literal: str, method_names: set[str]):
        self.selector_literal = selector_literal
        self.method_names = method_names
        self.changed = False

    def leave_SimpleStatementLine(
        self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine
    ) -> cst.BaseStatement | FlattenSentinel[cst.BaseStatement]:
        if len(updated_node.body) != 1:
            return updated_node

        stmt = updated_node.body[0]
        if not isinstance(stmt, cst.Expr) or not isinstance(stmt.value, cst.Call):
            return updated_node

        call = stmt.value
        if not isinstance(call.func, cst.Attribute):
            return updated_node

        if not (isinstance(call.func.value, cst.Name) and call.func.value.value == "page"):
            return updated_node

        if not isinstance(call.func.attr, cst.Name) or call.func.attr.value not in self.method_names:
            return updated_node

        if not call.args:
            return updated_node

        first_arg = call.args[0].value
        if not isinstance(first_arg, cst.SimpleString):
            return updated_node

        if first_arg.value != self.selector_literal:
            return updated_node

        # Insert: expect(page.locator("<selector>")).to_be_visible()
        self.changed = True
        expect_stmt = cst.parse_statement(
            f'expect(page.locator({self.selector_literal})).to_be_visible()'
        )
        return FlattenSentinel([expect_stmt, updated_node])


def insert_expect_visible_before_action(
    source: str, *, selector_literal: str, methods: set[str] | None = None
) -> CstPatchResult:
    """
    AST-safe patch for the common Playwright failure mode:
    "waiting for selector ..." / timeout while clicking or filling.

    `selector_literal` must include quotes, e.g. "\"#submit\"" or "'#submit'".
    """
    methods = methods or {"click", "fill"}
    try:
        module = cst.parse_module(source)
    except Exception as e:  # noqa: BLE001
        return CstPatchResult(False, f"Parse failed: {e}")

    transformer = _ExpectVisibleInserter(selector_literal=selector_literal, method_names=set(methods))
    updated = module.visit(transformer)
    if not transformer.changed:
        return CstPatchResult(False, "No matching Playwright call found.")
    return CstPatchResult(True, "Inserted expect(...).to_be_visible()", updated.code)

