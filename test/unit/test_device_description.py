"""
DESCRIPTION FILE TESTS (pc_tool/device_description.py)

Coverage:
1. SVD by the CMSIS-SVD rules: dim arrays and dimIndex labels, clusters (nested, arrays),
   derivedFrom on peripherals, clusters and registers (same scope and full path), peripheral
   arrays, size/access inherited device -> peripheral -> cluster -> register, alternateGroup
   names, namespaced files, scaled numbers
2. A real NXP MCX file (excerpt of MCXA256.svd, BSD-3-Clause): derived peripherals, alternate
   registers, cluster arrays, dimIndex
3. ATDF: memory segments, sizes in bytes (16-bit registers cover 2 addresses), rw access
4. Errors: unknown file type, missing file, broken XML, an ATDF for another part
"""

import tempfile
from pathlib import Path

from pc_tool import device_description, target_model
from pc_tool.device_description import DescriptionError
from test.common.asserts import assert_eq

_FIXTURES = Path(__file__).parent / "fixtures"
_MCU_DB = target_model.MCU_DB


def _svd(peripherals: str, device_extra: str = "") -> device_description.Description:
    """Read an SVD made of *peripherals* (XML) and optional device-level elements."""
    text = f"<device><name>TEST</name>{device_extra}<peripherals>{peripherals}</peripherals></device>"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.svd"
        path.write_text(text)
        return device_description.read_description(path, "test")


def _addresses(description) -> dict[str, int]:
    return {f"{r.peripheral}_{r.name}": r.address for p in description.peripherals for r in p.registers}


_ARRAYS = """
<peripheral>
  <name>TST</name><baseAddress>0x40000000</baseAddress>
  <registers>
    <register><name>PLAIN</name><addressOffset>0x0</addressOffset></register>
    <register><name>SET[%s]</name><dim>4</dim><dimIncrement>0x4</dimIncrement><addressOffset>0x220</addressOffset></register>
    <register><name>WD%s</name><dim>3</dim><dimIncrement>0x4</dimIncrement><dimIndex>0,1,5</dimIndex>
      <addressOffset>0x300</addressOffset></register>
    <register><name>R%s</name><dim>3</dim><dimIncrement>0x8</dimIncrement><dimIndex>2-4</dimIndex>
      <addressOffset>0x400</addressOffset></register>
    <cluster><name>CH[%s]</name><dim>4</dim><dimIncrement>0x10</dimIncrement><addressOffset>0x40</addressOffset>
      <register><name>CTRL</name><addressOffset>0x4</addressOffset></register>
      <register><name>D%s</name><dim>2</dim><dimIncrement>0x4</dimIncrement><addressOffset>0x8</addressOffset></register>
    </cluster>
    <cluster><name>SOLO</name><addressOffset>0x100</addressOffset>
      <register><name>X</name><addressOffset>0x8</addressOffset></register>
      <cluster><name>INNER</name><addressOffset>0x20</addressOffset>
        <register><name>Y</name><addressOffset>0x4</addressOffset></register>
      </cluster>
    </cluster>
  </registers>
</peripheral>
"""


# ---------------------------------------------------------------- 1. SVD rules

def test_dim_arrays_and_index_labels():
    a = _addresses(_svd(_ARRAYS))
    base = 0x40000000
    assert_eq(a["TST_PLAIN"], base)
    assert_eq([a[f"TST_SET{i}"] for i in range(4)], [base + 0x220 + 4 * i for i in range(4)])
    assert_eq((a["TST_WD0"], a["TST_WD1"], a["TST_WD5"]), (base + 0x300, base + 0x304, base + 0x308))
    assert_eq((a["TST_R2"], a["TST_R3"], a["TST_R4"]), (base + 0x400, base + 0x408, base + 0x410))
    assert "TST_WD2" not in a and "TST_SET[%s]" not in a and "TST_SET4" not in a


def test_clusters_join_names_and_add_offsets():
    a = _addresses(_svd(_ARRAYS))
    base = 0x40000000
    assert_eq([a[f"TST_CH{i}_CTRL"] for i in range(4)], [base + 0x40 + 0x10 * i + 0x4 for i in range(4)])
    assert_eq(a["TST_CH2_D1"], base + 0x40 + 0x20 + 0x8 + 0x4)
    assert_eq(a["TST_SOLO_X"], base + 0x108)
    assert_eq(a["TST_SOLO_INNER_Y"], base + 0x100 + 0x20 + 0x4)              # nested cluster
    assert_eq(len(a), 1 + 4 + 3 + 3 + 4 * 3 + 2)


def test_peripheral_derived_from_another_takes_its_registers_at_its_own_base():
    d = _svd("""
      <peripheral><name>UART0</name><description>UART</description><baseAddress>0x40001000</baseAddress>
        <registers><register><name>DATA</name><addressOffset>0x4</addressOffset></register></registers>
      </peripheral>
      <peripheral derivedFrom="UART0"><name>UART1</name><baseAddress>0x40002000</baseAddress></peripheral>""")
    uart1 = d.peripherals[1]
    assert_eq((uart1.name, uart1.base, uart1.description), ("UART1", 0x40002000, "UART"))
    assert_eq([(r.name, r.address) for r in uart1.registers], [("DATA", 0x40002004)])


def test_peripheral_array():
    d = _svd("""
      <peripheral><name>GPIO%s</name><dim>3</dim><dimIncrement>0x400</dimIncrement><dimIndex>A-C</dimIndex>
        <baseAddress>0x48000000</baseAddress>
        <registers><register><name>ODR</name><addressOffset>0x14</addressOffset></register></registers>
      </peripheral>""")
    assert_eq([(p.name, p.base) for p in d.peripherals],
              [("GPIOA", 0x48000000), ("GPIOB", 0x48000400), ("GPIOC", 0x48000800)])
    assert_eq(_addresses(d)["GPIOC_ODR"], 0x48000814)


def test_register_derived_in_the_same_scope_and_by_full_path():
    d = _svd("""
      <peripheral><name>TIM0</name><baseAddress>0x40010000</baseAddress>
        <registers>
          <register><name>CCR0</name><addressOffset>0x10</addressOffset><size>16</size><access>read-only</access></register>
          <register derivedFrom="CCR0"><name>CCR1</name><addressOffset>0x14</addressOffset></register>
          <cluster><name>CH</name><addressOffset>0x40</addressOffset>
            <register><name>CFG</name><addressOffset>0x0</addressOffset><size>8</size></register>
          </cluster>
        </registers>
      </peripheral>
      <peripheral><name>TIM1</name><baseAddress>0x40020000</baseAddress>
        <registers>
          <register derivedFrom="TIM0.CCR0"><name>CMP</name><addressOffset>0x8</addressOffset><access>read-write</access></register>
          <cluster derivedFrom="TIM0.CH"><name>CHX</name><addressOffset>0x80</addressOffset></cluster>
        </registers>
      </peripheral>""")
    regs = {f"{r.peripheral}_{r.name}": r for p in d.peripherals for r in p.registers}
    ccr1, cmp_, cfg = regs["TIM0_CCR1"], regs["TIM1_CMP"], regs["TIM1_CHX_CFG"]
    assert_eq((ccr1.address, ccr1.size, ccr1.writable), (0x40010014, 2, False))   # inherited size and access
    assert_eq((cmp_.address, cmp_.size, cmp_.writable), (0x40020008, 2, True))    # own access wins
    assert_eq((cfg.address, cfg.size), (0x40020080, 1))                           # derived cluster, its registers


def test_size_and_access_are_inherited_level_by_level():
    d = _svd("""
      <peripheral><name>P</name><baseAddress>0x40000000</baseAddress><size>16</size>
        <registers>
          <register><name>A</name><addressOffset>0x0</addressOffset></register>
          <cluster><name>C</name><addressOffset>0x10</addressOffset><size>8</size><access>read-write</access>
            <register><name>B</name><addressOffset>0x0</addressOffset></register>
          </cluster>
        </registers>
      </peripheral>
      <peripheral><name>Q</name><baseAddress>0x40001000</baseAddress>
        <registers><register><name>D</name><addressOffset>0x0</addressOffset></register></registers>
      </peripheral>""", device_extra="<size>32</size><access>read-only</access>")
    regs = {f"{r.peripheral}_{r.name}": (r.size, r.writable) for p in d.peripherals for r in p.registers}
    assert_eq(regs, {"P_A": (2, False), "P_C_B": (1, True), "Q_D": (4, False)})


def test_unstated_size_and_access_fall_back_to_32_bit_read_write():
    reg = _svd(_ARRAYS).peripherals[0].registers[0]
    assert_eq((reg.size, reg.writable), (4, True))


def test_alternate_register_reusing_a_name_gets_its_group_suffix():
    d = _svd("""
      <peripheral><name>I3C</name><baseAddress>0x40002000</baseAddress>
        <registers>
          <register><name>DATA</name><addressOffset>0x54</addressOffset><access>write-only</access></register>
          <register><name>DATA</name><alternateGroup>BYTE</alternateGroup><addressOffset>0x54</addressOffset>
            <size>8</size></register>
        </registers>
      </peripheral>""")
    assert_eq([(r.name, r.address, r.size) for r in d.peripherals[0].registers],
              [("DATA", 0x40002054, 4), ("DATA_BYTE", 0x40002054, 1)])


def test_namespaced_file_and_scaled_numbers():
    text = """<svd:device xmlns:svd="http://example.com/svd"><svd:peripherals><svd:peripheral>
      <svd:name>N</svd:name><svd:baseAddress>4k</svd:baseAddress><svd:registers>
      <svd:register><svd:name>R</svd:name><svd:addressOffset>#1000</svd:addressOffset></svd:register>
      </svd:registers></svd:peripheral></svd:peripherals></svd:device>"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ns.svd"
        path.write_text(text)
        d = device_description.read_description(path, "n")
    assert_eq(_addresses(d), {"N_R": 4096 + 8})


# ---------------------------------------------------------------- 2. a real NXP MCX file

def test_nxp_mcx_excerpt():
    d = device_description.read_description(_FIXTURES / "MCXA256_excerpt.svd", "mcxa256")
    by_name = {p.name: p for p in d.peripherals}
    assert_eq(sorted(by_name), ["CTIMER0", "CTIMER1", "FMU0", "FREQME0", "VBAT0"])

    ctimer0, ctimer1 = by_name["CTIMER0"], by_name["CTIMER1"]                     # derivedFrom
    assert_eq((ctimer1.base, len(ctimer1.registers)), (0x40005000, len(ctimer0.registers)))
    assert_eq([r.address - ctimer1.base for r in ctimer1.registers], [r.address - ctimer0.base for r in ctimer0.registers])

    freqme = {r.name: r for r in by_name["FREQME0"].registers}                    # alternate views of one address
    assert_eq((freqme["CTRL_R"].address, freqme["CTRL_R"].writable), (0x40009000, False))
    assert_eq((freqme["CTRL_W"].address, freqme["CTRL_W"].writable), (0x40009000, True))

    vbat = {r.name: r.address for r in by_name["VBAT0"].registers}                # cluster array
    assert_eq((vbat["WAKEUP0_WAKEUPA"], vbat["WAKEUP1_WAKEUPA"]), (0x40093700, 0x40093708))

    fccob = [r.name for r in by_name["FMU0"].registers if r.name.startswith("FCCOB")]   # dimIndex
    assert_eq(fccob[:3], ["FCCOB0", "FCCOB1", "FCCOB2"])


# ---------------------------------------------------------------- 3. ATDF

def test_atdf_segments_and_16_bit_registers():
    d = device_description.read_description(_MCU_DB / "avr" / "atmega" / "ATmega328P.atdf", "atmega328p")
    segments = {s.name: (s.kind, s.start, s.size) for s in d.segments}
    assert_eq(segments["FLASH"], ("flash", 0, 0x8000))
    assert_eq(segments["IRAM"], ("ram", 0x100, 0x800))
    ubrr0 = target_model.Registers(d.peripherals).by_name("UBRR0")
    assert_eq((ubrr0.peripheral, ubrr0.address, ubrr0.size), ("USART", 0xC4, 2))   # 0xC5 (high byte) is in it too


def test_atdf_rw_attribute():
    d = device_description.read_description(_MCU_DB / "avr" / "atmega" / "ATmega4809.atdf", "atmega4809")
    access = {}
    for p in d.peripherals:
        for r in p.registers:
            access.setdefault(r.writable, r.name)
    assert_eq(set(access), {True, False})                                       # R is read-only, RW/W writable


# ---------------------------------------------------------------- 4. errors

def test_errors_name_the_problem():
    with tempfile.TemporaryDirectory() as tmp:
        broken = Path(tmp) / "broken.svd"
        broken.write_text("<device><peripherals>")
        cases = [
            (Path(tmp) / "part.txt", "x", "No parser for 'part.txt'"),
            (Path(tmp) / "missing.svd", "x", "MCU description file not found"),
            (broken, "x", "Invalid SVD XML"),
            (_MCU_DB / "avr" / "atmega" / "ATmega328P.atdf", "atmega48", "ATDF device mismatch"),
        ]
        for path, mcu, message in cases:
            try:
                device_description.read_description(path, mcu)
            except DescriptionError as exc:
                assert message in str(exc), (message, str(exc))
                continue
            raise AssertionError(f"{path.name} for {mcu} was accepted")
