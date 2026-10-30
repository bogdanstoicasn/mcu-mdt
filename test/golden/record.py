"""Re-record the golden expectations: python3 -m test.golden.record

Run it only for a deliberate change of behavior, and review the diff of test/golden/expected/
before committing it: every changed line is a change users will see on the wire or on screen.
"""

from test.common import fake_mcu
from test.golden.golden_cases import cases, contract, expected_path, run_case


def main() -> None:
    server, port = fake_mcu.serve()
    try:
        for part, name, script in cases():
            path = expected_path(part, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(contract(run_case(part, script, port))) + "\n")
            print(f"recorded {path.relative_to(path.parents[2])}")
    finally:
        server.close()


if __name__ == "__main__":
    main()
