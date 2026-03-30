import importlib
import os
import traceback
import sys


class PyMDTest:
    def __init__(self, test_dir=None, category=None):
        # Always resolve test_dir relative to this file
        if test_dir is None:
            test_dir = os.path.dirname(os.path.abspath(__file__))

        self.test_dir = test_dir
        self.category = category
        self.results = []

        # Ensure project root is importable
        project_root = os.path.abspath(os.path.join(self.test_dir, ".."))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def discover(self):
        test_modules = []

        print("[DEBUG] scanning:", os.path.abspath(self.test_dir))
        print("[DEBUG] exists:", os.path.exists(self.test_dir))

        for root_dir, _, files in os.walk(self.test_dir):
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    module_path = os.path.join(root_dir, file)

                    rel_path = os.path.relpath(module_path, self.test_dir)
                    module_name = rel_path.replace(os.sep, ".")[:-3]

                    # Build full module path correctly
                    module_name = f"{os.path.basename(self.test_dir)}.{module_name}"

                    if self.category is None or self.category in module_name:
                        test_modules.append(module_name)

        print("[DEBUG] discovered modules:", test_modules)
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
        name = f"{module_name.split('.')[-1]}::{test_func.__name__}"

        try:
            test_func()
            print(f"[PASS] {name}")
            self.results.append((name, True))

        except AssertionError as AsE:
            print(f"[FAIL] {name}: {AsE}")
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