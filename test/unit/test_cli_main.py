"""
CLI TESTS (pc_tool/cli_main.py)

Coverage:
1. Arguments: build_info, --elf, --script
2. A lost link wakes the main thread again and again until the session shuts down: a signal that
   lands just before readline blocks wakes nothing (found on the emulated ATmega328P, 2 runs in 10)
"""

import signal
import time

from pc_tool import cli_main
from test.common.asserts import assert_eq


def test_arguments():
    args = cli_main.parse_args(["build/f030f4/build_info.yaml", "--elf", "app.elf", "--script", "s.txt"])
    assert_eq((args.build_info, args.elf, args.script), ("build/f030f4/build_info.yaml", "app.elf", "s.txt"))
    assert_eq((cli_main.parse_args(["b.yaml"]).elf, cli_main.parse_args(["b.yaml"]).script), (None, None))


def test_the_main_thread_is_woken_until_shutdown_starts():
    sent = []
    real_kill, real_handler = signal.pthread_kill, signal.getsignal(signal.SIGINT)
    signal.pthread_kill = lambda thread, sig: sent.append(sig)
    try:
        waker = cli_main._MainWaker()
        waker.start()
        time.sleep(1.2)
        waker.stop()
        count = len(sent)
        time.sleep(0.7)
        assert count >= 3, sent                          # at once, then every half second
        assert_eq(len(sent), count, what="wake-ups after stop()")
        assert_eq(set(sent), {signal.SIGINT})
        assert_eq(signal.getsignal(signal.SIGINT), signal.SIG_IGN, what="Ctrl-C during shutdown")
    finally:
        signal.pthread_kill = real_kill
        signal.signal(signal.SIGINT, real_handler)
