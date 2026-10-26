"""
BUILD SYSTEM DESCRIPTOR TESTS FOR MCU-MDT (STEP 1: AVR)

Checks the YAML descriptors in build_system/ without running any build:
structure, cross-references, and that they say the same thing as the rest of the repo.

Coverage:
1. Structure: tree_root / tree_trunk / tree_branch files, required and unknown keys, ranges
2. Cross-references: platform directories, file and directory paths (relative, existing)
3. AVR part allowlist: matches docs/avr/info.md and the host's ATDF database
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
