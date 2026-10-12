"""
SVD <dim> / <cluster> EXPANSION TESTS FOR MCU-MDT

Validates that the SVD loader expands register arrays and clusters into
individually addressable registers, and that the parser resolves them.

Coverage:
1. Plain registers are unchanged
2. <dim> arrays: 'X[%s]' and 'X%s' naming, increment, default 0..n-1 index
3. <dimIndex> as a list ("0,1,5") and as a range ("2-4")
4. <cluster> blocks (with and without <dim>), including a dim'd register
   inside a dim'd cluster
5. NAME[idx] spelling accepted by resolve_register_address
6. Out-of-range elements do not resolve
"""

import xml.etree.ElementTree as ET

from pc_tool.loader import MCUMetadata, _SVDLoader, _SVDXmlHelper
from pc_tool.parser import resolve_register_address
from test.common.asserts import assert_eq

_SVD = """
<device>
  <peripherals>
    <peripheral>
      <name>TST_PERIPH</name>
      <baseAddress>0x40000000</baseAddress>
      <registers>
        <register><name>PLAIN</name><addressOffset>0x0</addressOffset></register>
        <register>
          <name>SET[%s]</name><dim>4</dim><dimIncrement>0x4</dimIncrement>
          <addressOffset>0x220</addressOffset>
        </register>
        <register>
          <name>WD%s</name><dim>3</dim><dimIncrement>0x4</dimIncrement>
          <dimIndex>0,1,5</dimIndex><addressOffset>0x300</addressOffset>
        </register>
        <register>
          <name>R%s</name><dim>3</dim><dimIncrement>0x8</dimIncrement>
          <dimIndex>2-4</dimIndex><addressOffset>0x400</addressOffset>
        </register>
        <cluster>
          <name>CH[%s]</name><dim>4</dim><dimIncrement>0x10</dimIncrement>
          <addressOffset>0x40</addressOffset>
          <register><name>CTRL</name><addressOffset>0x4</addressOffset></register>
          <register>
            <name>D%s</name><dim>2</dim><dimIncrement>0x4</dimIncrement>
            <addressOffset>0x8</addressOffset>
          </register>
        </cluster>
        <cluster>
          <name>SOLO</name><addressOffset>0x100</addressOffset>
          <register><name>X</name><addressOffset>0x8</addressOffset></register>
        </cluster>
      </registers>
    </peripheral>
  </peripherals>
</device>
"""


def _metadata() -> dict:
    meta = MCUMetadata(device="tst", architecture=None, family=None)
    _SVDLoader._parse_peripherals(_SVDXmlHelper(ET.fromstring(_SVD), {}), meta)
    return meta.to_dict()


def _offsets() -> dict:
    regs = _metadata()["modules"]["TST_PERIPH"]["register_groups"]["TST_PERIPH"]["registers"]
    return {name: int(r["offset"]) for name, r in regs.items()}


def test_plain_register_unchanged():
    assert_eq(_offsets()["PLAIN"], 0x0)


def test_dim_array_expanded_with_increment():
    offs = _offsets()
    for i in range(4):
        assert_eq(offs[f"SET{i}"], 0x220 + 4 * i)
    assert "SET" not in offs and "SET[%s]" not in offs


def test_dimindex_list_uses_labels_but_positional_addresses():
    offs = _offsets()
    assert_eq((offs["WD0"], offs["WD1"], offs["WD5"]), (0x300, 0x304, 0x308))
    assert "WD2" not in offs


def test_dimindex_range():
    offs = _offsets()
    assert_eq((offs["R2"], offs["R3"], offs["R4"]), (0x400, 0x408, 0x410))


def test_cluster_with_dim_prefixes_and_offsets():
    offs = _offsets()
    for i in range(4):
        assert_eq(offs[f"CH{i}_CTRL"], 0x40 + 0x10 * i + 0x4)


def test_dim_register_inside_dim_cluster():
    offs = _offsets()
    assert_eq(offs["CH2_D1"], 0x40 + 0x10 * 2 + 0x8 + 0x4)


def test_cluster_without_dim():
    assert_eq(_offsets()["SOLO_X"], 0x100 + 0x8)


def test_total_register_count():
    # PLAIN + SET*4 + WD*3 + R*3 + CH*(CTRL + D*2)*4 + SOLO_X
    assert_eq(len(_offsets()), 1 + 4 + 3 + 3 + 4 * 3 + 1)


def test_resolve_array_element_and_bracket_spelling():
    md = _metadata()
    want = 0x40000000 + 0x220 + 4 * 2
    assert_eq(resolve_register_address("TST_PERIPH_SET2", md), want)
    assert_eq(resolve_register_address("tst_periph_set[2]", md), want)


def test_resolve_cluster_register():
    md = _metadata()
    assert_eq(resolve_register_address("TST_PERIPH_CH3_CTRL", md), 0x40000000 + 0x40 + 0x30 + 0x4)


def test_out_of_range_element_does_not_resolve():
    md = _metadata()
    assert_eq(resolve_register_address("TST_PERIPH_SET4", md), None)
    assert_eq(resolve_register_address("TST_PERIPH_WD2", md), None)
