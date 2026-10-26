#!/usr/bin/env python3
"""Turn the build_system YAML tree into the files a build needs.

    python3 build_system/generate.py <part> [key=value ...]
    python3 build_system/generate.py atmega328p F_CPU=8000000 BAUDRATE=38400

Finds the part's node, merges root -> trunk -> branch -> node -> leaf (the key=value
overrides, keys case-insensitive) and writes, under <files.build>/<part>/:
  build.mk         Make variables: toolchain, flags, sources, outputs, commands, dist files
  mdt_target.h     configuration and memory macros plus their checks, force-included in every .c
  memory.ld        the linker MEMORY regions (only for a target that describes its memory)
  build_info.yaml  what the PC tool needs: description file, port, baud rate, limits, memory map
and prints that directory, relative to the repository root, for the Makefile.

A file is rewritten only when its content changes, so Make can run this on every
build without forcing a full recompile.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / "build_system"

# Sections a trunk, a branch or a node may carry; deeper levels add to shallower ones.
SECTIONS = {"mdt_defaults", "features", "toolchain", "memory", "build", "commands", "dist", "host"}
LEVEL_KEYS = {
    "tree_trunk": {"version", "type", "platform"} | SECTIONS,
    "tree_branch": {"version", "type", "platform", "branch", "nodes"} | SECTIONS,
    "node": SECTIONS,
}
REQUIRED = (("toolchain", "prefix"), ("features", "uart_idle"), ("build", "lib"), ("build", "hal_dir"),
            ("build", "example"), ("build", "flags"), ("build", "outputs"), ("dist", "files"),
            ("dist", "makefile"), ("host", "mcu_db"))
REGION_KEYS = {"origin", "size", "page", "access"}
MAKE_TARGETS = {"all", "clean", "wipe", "clean_logs", "help"}   # a command may not take these names


class DescriptorError(Exception):
    """A part, leaf value or descriptor that cannot be built."""


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def check_keys(doc: dict, kind: str, where: str) -> None:
    unknown = set(doc) - LEVEL_KEYS[kind]
    if unknown:
        raise DescriptorError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")


def merge(base, override, where: str = ""):
    """Deeper level wins: mappings merge key by key, lists are appended, other values are replaced."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = merge(base[key], value, f"{where}.{key}") if key in base else value
        return merged
    if isinstance(base, list) and isinstance(override, list):
        return base + override
    if isinstance(base, (dict, list)) or isinstance(override, (dict, list)):
        raise DescriptorError(f"{where.lstrip('.')}: a {type(override).__name__} cannot replace a {type(base).__name__}")
    return override


def find_node(root: dict, part: str) -> tuple:
    """Return (platform, branch file, branch doc, node name as written) for a part, case-insensitive."""
    for platform in root["platform"]:
        for branch_path in sorted((TREE / platform).glob("tree_branch_*.yaml")):
            branch = load_yaml(branch_path)
            for node in branch["nodes"]:
                if node.lower() == part.lower():
                    return platform, branch_path, branch, node
    raise DescriptorError(f"unsupported part {part!r}: not a node in build_system/*/tree_branch_*.yaml")


def parse_leaf(pairs: list, defaults: dict) -> dict:
    """key=value strings -> values typed like the defaults they override."""
    leaf = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        key = key.lower()
        if not sep or key not in defaults:
            raise DescriptorError(f"unknown setting {pair!r}; known: {', '.join(sorted(defaults))}")
        leaf[key] = _coerce(key, raw.strip(), type(defaults[key]))
    return leaf


def _coerce(key: str, raw: str, kind: type):
    if kind is bool:
        if raw.lower() in ("1", "true", "yes", "on"):
            return True
        if raw.lower() in ("0", "false", "no", "off"):
            return False
    elif kind is int:
        try:
            return int(raw.rstrip("uUlL"), 0)   # accepts 16000000UL as written in Makefiles
        except ValueError:
            pass
    elif raw:
        return raw
    raise DescriptorError(f"{key}={raw!r} is not a valid {kind.__name__}")


def parse_bytes(value, where: str) -> int:
    """16384, 0x4000, '16K' or '1M' -> bytes."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    match = re.fullmatch(r"(0x[0-9a-fA-F]+|\d+)\s*([KM]?)", str(value).strip())
    if not match:
        raise DescriptorError(f"{where}: {value!r} is not a size (use 16384, 0x4000, 16K or 1M)")
    return int(match.group(1), 0) * {"": 1, "K": 1024, "M": 1024 * 1024}[match.group(2)]


def parse_memory(memory: dict) -> dict:
    """The merged memory section -> {region: {origin, size, page, access}} with integers."""
    regions = {}
    for name, region in memory.items():
        where = f"memory.{name}"
        if not isinstance(region, dict) or set(region) - REGION_KEYS:
            raise DescriptorError(f"{where}: allowed keys are {', '.join(sorted(REGION_KEYS))}")
        missing = {"origin", "size", "access"} - set(region)
        if missing:
            raise DescriptorError(f"{where}: missing {', '.join(sorted(missing))} (sizes belong on the node)")
        regions[name] = {
            "origin": parse_bytes(region["origin"], f"{where}.origin"),
            "size": parse_bytes(region["size"], f"{where}.size"),
            "page": parse_bytes(region["page"], f"{where}.page") if "page" in region else None,
            "access": str(region["access"]),
        }
    return regions


def validate(config: dict, desc: dict, memory: dict, platform: str) -> None:
    """Fail early with a clear message instead of a _Static_assert or a linker error later."""
    problems = []
    if config["f_cpu"] <= 0:
        problems.append("f_cpu must be > 0")
    if config["baudrate"] <= 0:
        problems.append("baudrate must be > 0")
    if config["buffer_size"] not in (32, 64, 128):
        problems.append("buffer_size must be 32, 64 or 128 (power of two, uint8_t index, holds one 18-byte packet)")
    for key in ("breakpoints", "watchpoints"):
        if not 1 <= config[key] <= 8:
            problems.append(f"{key} must be 1..8 (8-bit mask)")
    if config["uart_idle"] and not desc["features"]["uart_idle"]:
        problems.append(f"uart_idle=true is not supported on {platform}")
    for name, region in memory.items():
        page = region["page"]
        if region["size"] <= 0:
            problems.append(f"memory.{name}.size must be > 0")
        if page is not None and (page <= 0 or page & (page - 1) or region["size"] % page):
            problems.append(f"memory.{name}.page must be a power of two that divides the size")
    for name in desc.get("commands", {}):
        if name in MAKE_TARGETS:
            problems.append(f"command {name!r} would hide the Makefile's own target")
    if problems:
        raise DescriptorError("; ".join(problems))


def resolve(part: str, leaf_pairs: list = ()) -> dict:
    """Everything the output files need, from the tree plus the leaf."""
    root = load_yaml(TREE / "tree_root.yaml")
    platform, branch_path, branch, node = find_node(root, part)
    trunk_path = TREE / platform / "tree_trunk.yaml"
    trunk = load_yaml(trunk_path)
    node_doc = branch["nodes"][node] or {}
    check_keys(trunk, "tree_trunk", str(trunk_path.relative_to(ROOT)))
    check_keys(branch, "tree_branch", str(branch_path.relative_to(ROOT)))
    check_keys(node_doc, "node", f"{branch_path.relative_to(ROOT)}: node {node}")

    desc = {}
    for doc in (trunk, branch, node_doc):
        desc = merge(desc, {key: value for key, value in doc.items() if key in SECTIONS})

    defaults = merge(root["mdt_defaults"], desc.get("mdt_defaults", {}), "mdt_defaults")
    config = {**defaults, **parse_leaf(list(leaf_pairs), defaults)}
    missing = [f"{section}.{key}" for section, key in REQUIRED if key not in desc.get(section, {})]
    if missing:
        raise DescriptorError(f"{node}: {', '.join(missing)} missing from its trunk, branch and node")
    memory = parse_memory(desc.get("memory", {}))
    validate(config, desc, memory, platform)

    part_lower = node.lower()
    build_dir = f"{root['files']['build']}/{part_lower}"
    return {
        "root": root, "desc": desc, "platform": platform, "node": node, "part": part_lower,
        "config": config, "memory": memory, "build_dir": build_dir,
        "image": f"{build_dir}/{Path(config['elf']).stem}",
    }


def placeholders(target: dict) -> dict:
    values = {
        "mcu": target["part"], "node": target["node"], "build_dir": target["build_dir"],
        "image": target["image"], "port": target["config"]["port"],
    }
    for name, region in target["memory"].items():
        values[f"{name}_origin"] = f"0x{region['origin']:08X}"
        values[f"{name}_size"] = str(region["size"])
    return values


def render(text, values: dict, where: str) -> str:
    """Fill {name} placeholders; '{ ...' with a space (shell grouping) is left alone."""
    def fill(match):
        if match.group(1) not in values:
            raise DescriptorError(f"{where}: unknown placeholder {{{match.group(1)}}}; known: {', '.join(sorted(values))}")
        return values[match.group(1)]
    return re.sub(r"\{(\w+)\}", fill, str(text))


def _make_value(text: str) -> str:
    """A literal value for 'NAME := value' in Make: $ and # would be expanded or start a comment."""
    return text.replace("$", "$$").replace("#", r"\#")


def render_build_mk(target: dict) -> str:
    desc, values = target["desc"], placeholders(target)
    build, flags = desc["build"], desc["build"]["flags"]
    prefix = desc["toolchain"]["prefix"]

    def words(items, where):
        return " ".join(render(item, values, where) for item in items)

    variables = [
        ("CC", f"{prefix}gcc"), ("AR", f"{prefix}ar"), ("OBJCOPY", f"{prefix}objcopy"), ("SIZE", f"{prefix}size"),
        ("SRC_DIR", target["root"]["files"]["src"]),
        ("INC_DIR", target["root"]["files"]["inc"]),
        ("HAL_DIR", build["hal_dir"]),
        ("STARTUP", build.get("startup", "")),
        ("EXAMPLE", build["example"]),
        ("BUILD_DIR", target["build_dir"]),
        ("IMAGE", target["image"]),
        ("LIB", build["lib"]),
        ("CFLAGS", words(flags.get("compile", []), "build.flags.compile")),
        ("LDFLAGS", words(flags.get("link", []), "build.flags.link")),
        ("LDLIBS", words(flags.get("libs", []), "build.flags.libs")),
        ("OUTPUTS", " ".join(build["outputs"])),
        *((f"OBJCOPY_FLAGS_{ext}", " ".join(args)) for ext, args in build["outputs"].items()),
        ("COMMANDS", " ".join(desc.get("commands", {}))),
        *((f"CMD_{name}", render(cmd, values, f"commands.{name}")) for name, cmd in desc.get("commands", {}).items()),
        ("DIST_FILES", " ".join(desc["dist"]["files"])),
        ("DIST_MAKEFILE", desc["dist"]["makefile"]),
    ]
    lines = [f"# Generated by build_system/generate.py for {target['part']}. Do not edit: change the YAML instead."]
    lines += [f"{name} := {_make_value(value)}" for name, value in variables]
    return "\n".join(lines) + "\n"


def render_target_header(target: dict) -> str:
    config, part = target["config"], target["part"]
    memory_lines = []
    for name, region in target["memory"].items():
        macro = f"MDT_{name.upper()}"
        memory_lines.append(f"#define {macro}_ORIGIN".ljust(32) + f"0x{region['origin']:08X}UL")
        memory_lines.append(f"#define {macro}_SIZE".ljust(32) + f"0x{region['size']:X}UL")
        if region["page"] is not None:
            memory_lines.append(f"#define {macro}_PAGE_SIZE".ljust(32) + f"0x{region['page']:X}UL")
    memory_block = ("\n" + "\n".join(memory_lines) + "\n") if memory_lines else ""
    return f"""\
/* Generated by build_system/generate.py for {part}. Do not edit: change the YAML instead. */
#ifndef MDT_TARGET_H
#define MDT_TARGET_H

#define PLATFORM_{target['platform'].upper()} 1
#define MDT_TARGET_MCU "{part}"

#define F_CPU                   {config['f_cpu']}UL
#define MDT_FEATURE_UART_IDLE   {int(config['uart_idle'])}
#define MDT_UART_BAUDRATE       {config['baudrate']}
#define MDT_BUFFER_SIZE         {config['buffer_size']}
#define MDT_MAX_BREAKPOINTS     {config['breakpoints']}
#define MDT_MAX_WATCHPOINTS     {config['watchpoints']}
{memory_block}
/* Already checked by the generator; these catch a hand-edited copy of this file. */
_Static_assert((MDT_BUFFER_SIZE & (MDT_BUFFER_SIZE - 1)) == 0, "MDT_BUFFER_SIZE must be a power of 2");
_Static_assert(MDT_BUFFER_SIZE <= 255, "MDT_BUFFER_SIZE cannot exceed 255 (uint8_t index)");
_Static_assert(MDT_MAX_BREAKPOINTS <= 8, "MDT_MAX_BREAKPOINTS cannot exceed 8");
_Static_assert(MDT_MAX_WATCHPOINTS <= 8, "MDT_MAX_WATCHPOINTS cannot exceed 8 (active_mask is uint8_t)");

#endif /* MDT_TARGET_H */
"""


def _length(size: int) -> str:
    return f"{size // 1024}K" if size % 1024 == 0 else str(size)


def render_memory_ld(target: dict) -> str:
    regions = "\n".join(
        f"    {name} ({region['access']}) : ORIGIN = 0x{region['origin']:08X}, LENGTH = {_length(region['size'])}"
        for name, region in target["memory"].items()
    )
    return (f"/* Generated by build_system/generate.py for {target['part']}. Do not edit: change the YAML instead. */\n"
            f"MEMORY\n{{\n{regions}\n}}\n")


def render_build_info(target: dict) -> str:
    config, values = target["config"], placeholders(target)
    info = {
        "platform": target["platform"].upper(),
        "mcu": target["part"],
        "mcu_db": render(target["desc"]["host"]["mcu_db"], values, "host.mcu_db"),
        "port": config["port"],
        "baudrate": config["baudrate"],
        "uart_idle": config["uart_idle"],
        "breakpoints": config["breakpoints"],
        "watchpoints": config["watchpoints"],
        "elf": config["elf"],
    }
    lines = [f"{key}: {value if not isinstance(value, bool) else str(value).lower()}" for key, value in info.items()]
    if target["memory"]:
        lines.append("memory:")
        for name, region in target["memory"].items():
            page = f", page: {region['page']}" if region["page"] is not None else ""
            lines.append(f"  {name}: {{origin: 0x{region['origin']:08X}, size: {region['size']}{page}}}")
    return "\n".join(lines) + "\n"


def write_if_changed(path: Path, text: str) -> bool:
    """Keep the timestamp when nothing changed, so Make does not rebuild everything."""
    if path.is_file() and path.read_text() == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return True


def generate(part: str, leaf_pairs: list = (), out_dir: Path = None) -> Path:
    target = resolve(part, leaf_pairs)
    out_dir = out_dir or ROOT / target["build_dir"]
    files = {
        "build.mk": render_build_mk(target),
        "mdt_target.h": render_target_header(target),
        "build_info.yaml": render_build_info(target),
    }
    if target["memory"]:
        files["memory.ld"] = render_memory_ld(target)
    for name, text in files.items():
        write_if_changed(out_dir / name, text)
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("part", help="a node name, e.g. atmega328p or f030f4 (case-insensitive)")
    ap.add_argument("leaf", nargs="*", help="overrides, e.g. F_CPU=8000000 BAUDRATE=38400")
    args = ap.parse_args()
    try:
        out_dir = generate(args.part, args.leaf)
    except DescriptorError as exc:
        print(f"generate.py: error: {exc}", file=sys.stderr)
        return 1
    print(out_dir.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
