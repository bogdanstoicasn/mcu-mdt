"""
BUILD SYSTEM DESCRIPTOR TESTS FOR MCU-MDT

Checks the YAML descriptors in build_system/ without running any build:
structure, cross-references, and that they say the same thing as the rest of the repo.

Coverage:
1. Structure: tree_root / tree_trunk / tree_branch files, known keys, every node resolves
2. Cross-references: platform directories, paths (relative, existing), host description files
3. Part allowlists: each platform's nodes match its docs table (and AVR the ATDF database)
"""

import re
from pathlib import Path

import yaml

from build_system.generate import LEVEL_KEYS, SECTIONS, check_keys, placeholders, render, resolve
from test.common.asserts import assert_eq

_ROOT = Path(__file__).resolve().parents[2]
_TREE = _ROOT / "build_system"

_ROOT_KEYS = {"version", "type", "platform", "mdt_defaults", "files"}
_MDT_ROOT = {"port", "baudrate", "buffer_size", "breakpoints", "watchpoints", "elf"}
_FILES = {"src", "inc", "build"}
_DOCS = {"avr": "docs/avr/info.md", "stm32": "docs/stm32/info.md"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _root() -> dict:
    return _load(_TREE / "tree_root.yaml")


def _trunk(platform: str) -> dict:
    return _load(_TREE / platform / "tree_trunk.yaml")


def _branches(platform: str) -> dict:
    return {p.stem.removeprefix("tree_branch_"): _load(p)
            for p in sorted((_TREE / platform).glob("tree_branch_*.yaml"))}


def _nodes(platform: str) -> set:
    return {n.lower() for doc in _branches(platform).values() for n in doc["nodes"]}


def _all_nodes() -> list:
    return sorted(n for platform in _root()["platform"] for n in _nodes(platform))


# ---------------------------------------------------------------- 1. structure

def test_every_descriptor_has_a_known_type_and_only_known_keys():
    root = _root()
    assert_eq((root["version"], root["type"]), (1, "tree_root"))
    assert_eq(set(root), _ROOT_KEYS)
    for platform in root["platform"]:
        trunk = _trunk(platform)
        assert_eq((trunk["version"], trunk["type"]), (1, "tree_trunk"), platform=platform)
        check_keys(trunk, "tree_trunk", platform)
        for name, branch in _branches(platform).items():
            assert_eq((branch["version"], branch["type"]), (1, "tree_branch"), branch=name)
            check_keys(branch, "tree_branch", name)
            for node, doc in branch["nodes"].items():
                check_keys(doc or {}, "node", node)


def test_level_keys_are_the_sections_plus_identity():
    assert_eq(LEVEL_KEYS["node"], SECTIONS)
    assert SECTIONS.issubset(LEVEL_KEYS["tree_trunk"]) and SECTIONS.issubset(LEVEL_KEYS["tree_branch"])


def test_root_defaults_are_valid():
    root = _root()
    assert_eq(set(root["mdt_defaults"]), _MDT_ROOT)
    assert_eq(set(root["files"]), _FILES)
    d = root["mdt_defaults"]
    assert isinstance(d["baudrate"], int) and d["baudrate"] > 0
    assert d["buffer_size"] in (32, 64, 128), "ring buffer: power of two, holds one 18-byte packet"
    assert 1 <= d["breakpoints"] <= 8 and 1 <= d["watchpoints"] <= 8
    assert d["elf"].endswith(".elf") and d["port"].startswith("/dev/")


def test_every_node_resolves_to_a_complete_valid_target():
    nodes = _all_nodes()
    assert nodes
    for part in nodes:
        target = resolve(part)       # raises DescriptorError on a missing, unknown or invalid value
        assert_eq(target["part"], part)


def test_platform_defaults_respect_the_platform_features():
    for platform in _root()["platform"]:
        trunk = _trunk(platform)
        assert isinstance(trunk["features"]["uart_idle"], bool)
        if not trunk["features"]["uart_idle"]:
            assert_eq(trunk["mdt_defaults"]["uart_idle"], False, platform=platform)


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


def test_referenced_paths_are_relative_and_exist():
    files = _root()["files"]
    for key in ("src", "inc"):
        assert not files[key].startswith("/") and (_ROOT / files[key]).is_dir(), files[key]
    for part in _all_nodes():
        desc = resolve(part)["desc"]
        build, dist = desc["build"], desc["dist"]
        paths = [build["hal_dir"], build["example"], build.get("startup"), *dist["files"], dist["makefile"]]
        for path in filter(None, paths):
            assert not path.startswith("/"), f"{part}: {path!r} is absolute; descriptors use repo-relative paths"
            assert (_ROOT / path).exists(), f"{part}: {path} does not exist"
        if build.get("startup"):
            assert build["startup"].startswith(build["hal_dir"] + "/"), f"{part}: startup outside hal_dir"


def test_every_node_has_its_host_description_file():
    for part in _all_nodes():
        target = resolve(part)
        mcu_db = render(target["desc"]["host"]["mcu_db"], placeholders(target), "host.mcu_db")
        assert (_ROOT / "pc_tool" / "mcu_db" / mcu_db).is_file(), f"{part}: pc_tool/mcu_db/{mcu_db} missing"


# ---------------------------------------------------------------- 3. part allowlists

def _docs_parts(platform: str) -> set:
    text = (_ROOT / _DOCS[platform]).read_text()
    table = text[text.index("| MCU |"):]
    table = table[:table.find("\n\n")] if "\n\n" in table else table
    return {name.lower() for name in re.findall(r"\b(AT90\w+|ATmega\w+|ATtiny\w+|F0\d\d\w\w|F1\d\d\w\w)\b", table)}


def test_every_platform_allowlist_matches_its_docs_table():
    for platform in _root()["platform"]:
        assert_eq(_nodes(platform), _docs_parts(platform), platform=platform)


def test_every_avr_node_exists_in_the_atdf_database():
    known = {p.stem.lower() for p in (_ROOT / "pc_tool" / "mcu_db" / "avr" / "atmega").iterdir()}
    assert_eq(sorted(_nodes("avr") - known), [])
