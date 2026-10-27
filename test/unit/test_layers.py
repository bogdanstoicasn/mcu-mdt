"""
LAYER TESTS FOR THE PC TOOL

pc_tool is layered: a module may import only modules of a lower layer, only at the top of the
file, and as a module (from pc_tool import wire_protocol), not names from it. This keeps the domain
(wire format, target, parsing, rules) free of I/O and printing, and the dependencies one-way.

    app        cli_main, debug_session, user_console
    transport  event_pump, command_client, serial_link
    domain     command_rules, command_parser, target_model, elf_symbols, device_description
    protocol   wire_protocol

The table below is the architecture; change it on purpose, not to silence it. Every module must
be in it.
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
    "serial_link": 5,
    "command_client": 6,
    "event_pump": 6,
    "user_console": 7,
    "debug_session": 8,
    "cli_main": 9,
    "__main__": 10,
}


def test_every_module_is_in_the_table():
    modules = {path.stem for path in _PC_TOOL.glob("*.py")} - {"__init__"}
    assert_eq(sorted(modules - set(LAYERS)), [], what="modules missing from LAYERS")
    assert_eq(sorted(set(LAYERS) - modules), [], what="LAYERS entries with no module")
    assert_eq([p.name for p in _PC_TOOL.iterdir() if p.is_dir() and (p / "__init__.py").exists()], [],
              what="subpackages (pc_tool is flat)")


def _pc_tool_imports(tree: ast.Module) -> list[tuple[str, int, bool]]:
    """(imported pc_tool module, line, at top level?) for every pc_tool import in *tree*."""
    top_level = {id(node) for node in tree.body}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pc_tool"):
            if node.module == "pc_tool":
                found += [(alias.name, node.lineno, id(node) in top_level) for alias in node.names]
            else:
                found.append((f"names from {node.module}", node.lineno, id(node) in top_level))
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
        if imported.startswith("names from "):
            problems.append(f"line {line}: imports {imported}; import the module instead")
        elif not top_level:
            problems.append(f"line {line}: imports {imported} inside a function")
        elif imported not in LAYERS:
            problems.append(f"line {line}: imports {imported}, which is not in the layer table")
        elif LAYERS[imported] >= LAYERS[module]:
            problems.append(f"line {line}: imports {imported} (layer {LAYERS[imported]}) from layer {LAYERS[module]}")
    assert_eq(problems, [], module=module)
