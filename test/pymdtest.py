import importlib
import logging
import os
import sys
import traceback

from test.common.asserts import TestSkip

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

PASS, FAIL, SKIP = "pass", "fail", "skip"


# Logger control: tests run with the pc_tool logger muted (a test that checks a warning unmutes it)
def _silence_logger():
    logging.getLogger("pc_tool").setLevel(logging.CRITICAL)


def _restore_logger():
    logging.getLogger("pc_tool").setLevel(logging.DEBUG)


# Parametrize decorator
def parametrize(arg_names: str, cases: list):
    arg_list = [arg.strip() for arg in arg_names.split(",")]

    def decorator(func):
        func._parametrize = (arg_list, cases)
        return func

    return decorator


# Test Runner
class PyMDTest:
    def __init__(self, test_dir=None, category=None):
        """Initialize the test runner."""
        if test_dir is None:
            test_dir = os.path.dirname(os.path.abspath(__file__))

        self.test_dir = test_dir
        self.category = category
        self.results = []  # (name, PASS | FAIL | SKIP)

        # Add project root to sys.path
        project_root = os.path.abspath(os.path.join(self.test_dir, ".."))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def discover(self):
        """Discover test modules in the specified directory."""
        test_modules = []

        for root_dir, _, files in os.walk(self.test_dir):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    module_path = os.path.join(root_dir, file)

                    rel_path = os.path.relpath(module_path, self.test_dir)
                    module_name = rel_path.replace(os.sep, ".")[:-3]

                    module_name = f"{os.path.basename(self.test_dir)}.{module_name}"

                    if self.category is None or self.category in module_name:
                        test_modules.append(module_name)

        return test_modules

    def run(self):
        """Run all discovered tests."""
        modules = self.discover()

        for module_name in modules:
            try:
                module = importlib.import_module(module_name)
                self.run_module(module)
            except Exception as e:
                print(f"[ERROR] Failed to import {module_name}: {e}")
                traceback.print_exc()

        self.report()

    def run_module(self, module):
        """Run all test functions in a given module."""
        for attr in dir(module):
            if attr.startswith("test_"):
                test_func = getattr(module, attr)

                if callable(test_func):
                    self.run_test(test_func, module.__name__)

    def run_test(self, test_func, module_name):
        """Run a single test function, handling both normal and parametrized tests."""
        base_name = f"{module_name.split('.')[-1]}::{test_func.__name__}"

        if hasattr(test_func, "_parametrize"):
            _, cases = test_func._parametrize
            for i, case in enumerate(cases):
                self._run_one(f"{base_name}[{i}]", lambda case=case: test_func(*case))
        else:
            self._run_one(base_name, test_func)

    def _run_one(self, name, call):
        """Run one test call and record it as passed, failed or skipped."""
        try:
            _silence_logger()
            call()
            print(f"{GREEN}[PASS]{RESET} {name}")
            self.results.append((name, PASS))

        except TestSkip as e:
            print(f"{YELLOW}[SKIP]{RESET} {name}: {e}")
            self.results.append((name, SKIP))

        except AssertionError as e:
            print(f"{RED}[FAIL]{RESET} {name}: {e}")
            self.results.append((name, FAIL))

        except Exception as e:
            print(f"{RED}[ERROR]{RESET} {name}: {e}")
            traceback.print_exc()
            self.results.append((name, FAIL))

        finally:
            _restore_logger()

    def report(self):
        """Print a summary of test results."""
        total = len(self.results)
        passed = sum(1 for _, state in self.results if state == PASS)
        skipped = sum(1 for _, state in self.results if state == SKIP)
        failed = sum(1 for _, state in self.results if state == FAIL)
        skip_note = f", {skipped} skipped" if skipped else ""

        print("\nTEST SUMMARY")
        print(
            f"{GREEN}Passed: {passed}/{total}{skip_note}{RESET}"
            if failed == 0
            else f"{RED}Passed: {passed}/{total}{skip_note} — {failed} failed{RESET}"
        )


if __name__ == "__main__":
    category = sys.argv[1] if len(sys.argv) > 1 else None

    testRunner = PyMDTest(category=category)
    testRunner.run()
