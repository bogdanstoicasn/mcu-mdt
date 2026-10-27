"""
LAYER TESTS FOR THE PC TOOL

pc_tool is layered: a module may import only modules of a lower layer, and only at the top of the
file. This keeps the domain (wire format, target, parsing, rules) free of I/O and printing, and the
dependencies one-way. The table below is the architecture; change it on purpose, not to silence it.

Modules not in the table are the ones the rework has not replaced yet.
"""

import ast
from pathlib import Path

from test.common.asserts import assert_eq
from test.pymdtest import parametrize

_PC_TOOL = Path(__file__).resolve().parents[2] / "pc_tool"

# Lower number = lower layer. A module may import only modules with a smaller number.
LAYERS = {
    "wire_protocol": 0,
    "device_description": 1,
    "elf_symbols": 1,
    "target_model": 2,
    "command_parser": 3,
    "command_rules": 4,
}


def _pc_tool_imports(tree: ast.Module) -> list[tuple[str, int, bool]]:
    """(imported pc_tool module, line, at top level?) for every pc_tool import in *tree*."""
    top_level = {id(node) for node in tree.body}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pc_tool"):
            if node.module == "pc_tool":
                names = [alias.name for alias in node.names]
            else:
                names = [node.module.split(".", 1)[1]]
            found += [(name, node.lineno, id(node) in top_level) for name in names]
        elif isinstance(node, ast.Import):
            found += [(alias.name.split(".", 1)[1], node.lineno, id(node) in top_level)
                      for alias in node.names if alias.name.startswith("pc_tool.")]
    return found


@parametrize("module", [(name,) for name in LAYERS])
def test_module_imports_only_lower_layers(module):
    tree = ast.parse((_PC_TOOL / f"{module}.py").read_text())
    problems = []
    for imported, line, top_level in _pc_tool_imports(tree):
        if imported == "MdtError":                  # pc_tool/__init__.py: the base error, below every layer
            continue
        if not top_level:
            problems.append(f"line {line}: imports {imported} inside a function")
        elif imported not in LAYERS:
            problems.append(f"line {line}: imports {imported}, which is not in the layer table")
        elif LAYERS[imported] >= LAYERS[module]:
            problems.append(f"line {line}: imports {imported} (layer {LAYERS[imported]}) from layer {LAYERS[module]}")
    assert_eq(problems, [], module=module)
