"""
GOLDEN TESTS FOR MCU-MDT: the whole PC tool, run as a user runs it

Each case runs `mcu_mdt.py <build_info> --script <case>` against test/common/fake_mcu.py and
compares the session log's contract (see golden_cases.contract) with test/golden/expected/.

Run:     python3 -m test.pymdtest golden        (about 2 minutes: each run waits the 2 s reset delay)
Update:  python3 -m test.golden.record          (only for a deliberate change; review the diff)
"""

from test.common import fake_mcu
from test.common.asserts import assert_eq
from test.golden.golden_cases import cases, contract, expected_path, run_case
from test.pymdtest import parametrize

_SERVER, _PORT = fake_mcu.serve()


@parametrize("part,name,script", cases())
def test_golden(part, name, script):
    expected = expected_path(part, name).read_text().splitlines()
    got = contract(run_case(part, script, _PORT))
    assert_eq(got, expected, part=part, case=name, script=script.strip())
