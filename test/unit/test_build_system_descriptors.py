"""
BUILD SYSTEM DESCRIPTOR TESTS FOR MCU-MDT (STEP 1: AVR)

Checks the YAML descriptors in build_system/ without running any build:
structure, cross-references, and that they say the same thing as the rest of the repo.

Coverage:
1. Structure: tree_root / tree_trunk / tree_branch files, required and unknown keys, ranges
2. Cross-references: platform directories, file and directory paths (relative, existing)
3. AVR part allowlist: matches docs/avr/info.md and the host's ATDF database
4. Equivalence with hal/avr/Makefile (transitional: remove with the Makefile)
"""

import re
from pathlib import Path

import yaml

from test.common.asserts import assert_eq

_ROOT = Path(__file__).resolve().parents[2]
_TREE = _ROOT / "build_system"

# The schema as of this step. A key that is not listed is an error (it would be ignored).
_KEYS = {
    "tree_root": {"version", "type", "platform", "mdt_defaults", "files"},
    "tree_trunk": {"version", "type", "platform", "mdt_defaults", "features", "toolchain", "build", "flash", "dist"},
    "tree_branch": {"version", "type", "platform", "branch", "nodes"},
}
_MDT_ROOT = {"port", "baudrate", "buffer_size", "breakpoints", "watchpoints", "elf"}
_FILES = {"src", "inc", "build"}
_BUILD = {"lib", "hal_dir", "example_dir", "part_flag", "flags", "hex"}
_DIST = {"headers", "example", "empty"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _root() -> dict:
    return _load(_TREE / "tree_root.yaml")


def _trunk(platform: str) -> dict:
    return _load(_TREE / platform / "tree_trunk.yaml")


def _branches(platform: str) -> dict:
    return {p.stem.removeprefix("tree_branch_"): _load(p)
            for p in sorted((_TREE / platform).glob("tree_branch_*.yaml"))}


def _all_files() -> list:
    return [_TREE / "tree_root.yaml", *sorted(_TREE.glob("*/tree_trunk.yaml")),
            *sorted(_TREE.glob("*/tree_branch_*.yaml"))]


def _check_keys(path: Path, doc: dict, expected: set) -> None:
    assert_eq(set(doc), expected, file=str(path.relative_to(_ROOT)))


# ---------------------------------------------------------------- 1. structure

def test_every_descriptor_has_a_known_type_and_only_known_keys():
    for path in _all_files():
        doc = _load(path)
        assert_eq(doc["version"], 1, file=path.name)
        expected_type = ("tree_root" if path.name == "tree_root.yaml"
                         else "tree_trunk" if path.name == "tree_trunk.yaml" else "tree_branch")
        assert_eq(doc["type"], expected_type, file=path.name)
        _check_keys(path, doc, _KEYS[expected_type])


def test_root_defaults_are_valid():
    root = _root()
    assert_eq(set(root["mdt_defaults"]), _MDT_ROOT)
    assert_eq(set(root["files"]), _FILES)
    d = root["mdt_defaults"]
    assert isinstance(d["baudrate"], int) and d["baudrate"] > 0
    assert d["buffer_size"] in (32, 64, 128), "ring buffer: power of two, holds one 18-byte packet"
    assert 1 <= d["breakpoints"] <= 8 and 1 <= d["watchpoints"] <= 8
    assert d["elf"].endswith(".elf") and d["port"].startswith("/dev/")


def test_trunk_sections_are_complete_and_consistent():
    for platform in _root()["platform"]:
        trunk = _trunk(platform)
        assert_eq(set(trunk["build"]), _BUILD, platform=platform)
        assert_eq(set(trunk["dist"]), _DIST, platform=platform)
        assert_eq(set(trunk["build"]["flags"]), {"compile", "link"}, platform=platform)
        assert isinstance(trunk["mdt_defaults"]["f_cpu"], int) and trunk["mdt_defaults"]["f_cpu"] > 0
        assert isinstance(trunk["features"]["uart_idle"], bool)
        if not trunk["features"]["uart_idle"]:
            assert_eq(trunk["mdt_defaults"]["uart_idle"], False, platform=platform)   # default cannot exceed the feature


def test_branches_point_back_to_their_platform_and_name():
    for platform in _root()["platform"]:
        assert _branches(platform), f"{platform} has no branch files"
        for name, doc in _branches(platform).items():
            assert_eq((doc["platform"], doc["branch"]), (platform, name))
            assert isinstance(doc["nodes"], dict) and doc["nodes"]
            assert all(isinstance(v, dict) for v in doc["nodes"].values())


def test_node_names_are_unique_across_the_tree():
    names = [n.lower() for platform in _root()["platform"] for doc in _branches(platform).values() for n in doc["nodes"]]
    assert_eq(len(names), len(set(names)))


# ---------------------------------------------------------------- 2. cross-references

def test_every_listed_platform_has_a_trunk_matching_its_directory():
    for platform in _root()["platform"]:
        assert (_TREE / platform / "tree_trunk.yaml").is_file(), platform
        assert_eq(_trunk(platform)["platform"], platform)


def test_no_descriptor_holds_an_absolute_path():
    paths = list(_root()["files"].values())
    for platform in _root()["platform"]:
        paths += [_trunk(platform)["build"]["hal_dir"], _trunk(platform)["build"]["example_dir"]]
    for p in paths:
        assert not p.startswith("/"), f"{p!r} is absolute; descriptors use paths relative to the repo root"


def test_referenced_directories_and_files_exist():
    files = _root()["files"]
    for key in ("src", "inc"):
        assert (_ROOT / files[key]).is_dir(), files[key]
    for platform in _root()["platform"]:
        build, dist = _trunk(platform)["build"], _trunk(platform)["dist"]
        assert (_ROOT / build["hal_dir"]).is_dir() and (_ROOT / build["example_dir"]).is_dir()
        for header in dist["headers"]:
            assert (_ROOT / files["inc"] / header).is_file(), header
        for name in dist["example"].values():
            assert (_ROOT / build["example_dir"] / name).is_file(), name


# ---------------------------------------------------------------- 3. AVR part allowlist

def _avr_nodes() -> set:
    return {n.lower() for doc in _branches("avr").values() for n in doc["nodes"]}


def test_avr_allowlist_matches_the_docs_table():
    docs = (_ROOT / "docs" / "avr" / "info.md").read_text()
    in_docs = {name.lower() for name in re.findall(r"\b(AT90\w+|ATmega\w+|ATtiny\w+)\b", docs[docs.index("| MCU |"):])}
    assert_eq(_avr_nodes(), in_docs)


def test_every_avr_node_exists_in_the_host_database():
    known = {p.stem.lower() for p in (_ROOT / "pc_tool" / "mcu_db" / "avr" / "atmega").iterdir()}
    assert_eq(sorted(_avr_nodes() - known), [])


def test_avr_has_exactly_the_supported_parts():
    assert_eq(len(_avr_nodes()), 80)


# ---------------------------------------------------------------- 4. equivalence with hal/avr/Makefile (transitional)

_MAKEFILE = (_ROOT / "hal" / "avr" / "Makefile").read_text()


def _make_tokens(variable: str) -> list:
    tokens = []
    for line in _MAKEFILE.splitlines():
        m = re.match(rf"{variable}\s*[:+?]?=\s*(.*)", line)
        if m:
            tokens += m.group(1).split("#")[0].split()
    return tokens


def _make_value(variable: str) -> str:
    values = _make_tokens(variable)
    assert len(values) == 1, f"{variable}: {values}"
    return values[0]


def test_avr_toolchain_and_names_match_the_makefile():
    avr, root = _trunk("avr"), _root()
    prefix = avr["toolchain"]["prefix"]
    for var, tool in (("CC", "gcc"), ("AR", "ar"), ("OBJCOPY", "objcopy"), ("SIZE", "size")):
        assert_eq(_make_value(var), prefix + tool, variable=var)
    assert_eq(_make_value("LIB_NAME"), f"lib{avr['build']['lib']}.a")
    assert f"-l{avr['build']['lib']} " in _MAKEFILE
    assert_eq(_make_value("ELF_NAME"), root["mdt_defaults"]["elf"])
    assert_eq(_make_value("HEX_NAME"), Path(root["mdt_defaults"]["elf"]).stem + ".hex")
    assert_eq(_make_value("EXAMPLES_DIR").removeprefix("../../"), avr["build"]["example_dir"])
    assert_eq(_make_value("BUILD_DIR").removeprefix("../../").removesuffix("/$(MCU)"), root["files"]["build"])
    assert_eq("hal/avr", avr["build"]["hal_dir"])        # the Makefile lives there and uses HAL_DIR := .


def test_avr_flags_match_the_makefile():
    avr = _trunk("avr")
    part = avr["build"]["part_flag"] + "$(MCU)"
    # flags the Makefile derives from other settings or needs for its own recipe: not data
    derived = ["-MMD", "-MP", "$(INCLUDES)", "-I$(HAL_DIR)", "-DF_CPU=$(F_CPU)", "-DPLATFORM_AVR",
               "-DMDT_FEATURE_UART_IDLE=$(MDT_USE_UART_IDLE)"]
    assert_eq(sorted(_make_tokens("CFLAGS")), sorted([part, *avr["build"]["flags"]["compile"], *derived]))
    assert_eq(sorted(_make_tokens("LDFLAGS")), sorted([part, *avr["build"]["flags"]["link"]]))


def test_avr_defaults_match_the_makefile():
    avr, root = _trunk("avr"), _root()
    assert_eq(int(re.sub(r"\D", "", _make_value("F_CPU"))), avr["mdt_defaults"]["f_cpu"])
    assert_eq(bool(int(_make_value("MDT_USE_UART_IDLE"))), avr["mdt_defaults"]["uart_idle"])
    port = re.search(r"^PORT\s*\?=\s*(\S+)", (_ROOT / "Makefile").read_text(), re.M).group(1)
    assert_eq(port, root["mdt_defaults"]["port"])


def test_avr_recipes_match_the_makefile():
    avr = _trunk("avr")
    objcopy = re.search(r"\$\(OBJCOPY\)\s+(.*?)\s+\$\(EXAMPLE_ELF\)", _MAKEFILE).group(1).split()
    assert_eq(objcopy, avr["build"]["hex"])
    flash = re.search(r"\bavrdude\s+(.*)", _MAKEFILE).group(1).split()
    assert_eq(flash[flash.index("-c") + 1], avr["flash"]["programmer"])
    assert_eq(int(flash[flash.index("-b") + 1]), avr["flash"]["programmer_baud"])
    assert_eq(avr["flash"]["tool"], "avrdude")
    headers = re.findall(r"cp \$\(INC_DIR\)/(\S+)", _MAKEFILE)
    assert_eq(headers, avr["dist"]["headers"])
    assert re.search(rf"cp \$\(EXAMPLES_DIR\)/{avr['dist']['example']['main']}\s", _MAKEFILE)
    assert re.search(rf"cp \$\(EXAMPLES_DIR\)/{avr['dist']['example']['makefile']}\s+\$\(BUILD_DIR\)/Makefile\.example", _MAKEFILE)
    assert_eq(re.findall(r"touch \$\(BUILD_DIR\)/(\S+)", _MAKEFILE), avr["dist"]["empty"])


def test_avr_build_info_keys_match_the_makefile():
    avr = _trunk("avr")
    keys = re.findall(r'echo "(\w+): ', _MAKEFILE.split("build_info.yaml:")[1].split("flash:")[0])
    assert_eq(keys, ["platform", "mcu", "port", "elf"])
    assert 'echo "platform: AVR"' in _MAKEFILE and avr["platform"].upper() == "AVR"
