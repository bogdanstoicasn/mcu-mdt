import importlib
import os
import traceback
import sys


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
        if test_dir is None:
            test_dir = os.path.dirname(os.path.abspath(__file__))

        self.test_dir = test_dir
        self.category = category
        self.results = []

        # Add project root to sys.path
        project_root = os.path.abspath(os.path.join(self.test_dir, ".."))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def discover(self):
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
        for attr in dir(module):
            if attr.startswith("test_"):
                test_func = getattr(module, attr)

                if callable(test_func):
                    self.run_test(test_func, module.__name__)

    def run_test(self, test_func, module_name):
        base_name = f"{module_name.split('.')[-1]}::{test_func.__name__}"

        # PARAMETRIZED TEST
        if hasattr(test_func, "_parametrize"):
            arg_names, cases = test_func._parametrize

            for i, case in enumerate(cases):
                name = f"{base_name}[{i}]"

                try:
                    test_func(*case)
                    print(f"[PASS] {name}")
                    self.results.append((name, True))

                except AssertionError as e:
                    print(f"[FAIL] {name}: {e}")
                    self.results.append((name, False))

                except Exception as e:
                    print(f"[ERROR] {name}: {e}")
                    traceback.print_exc()
                    self.results.append((name, False))
        else:
            # NORMAL TEST
            name = base_name

            try:
                test_func()
                print(f"[PASS] {name}")
                self.results.append((name, True))

            except AssertionError as e:
                print(f"[FAIL] {name}: {e}")
                self.results.append((name, False))

            except Exception as e:
                print(f"[ERROR] {name}: {e}")
                traceback.print_exc()
                self.results.append((name, False))

    def report(self):
        total_len = len(self.results)
        passed_len = sum(1 for _, passed in self.results if passed)

        print("\nTEST SUMMARY")
        print(f"Passed: {passed_len}/{total_len}")


if __name__ == "__main__":
    category = sys.argv[1] if len(sys.argv) > 1 else None

    testRunner = PyMDTest(category=category)
    testRunner.run()