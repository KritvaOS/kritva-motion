"""Import direction and purity of the source (KOS-MOTION-004 governing rules 4 and 5, AC-407).

The engine, the stores, admission and configuration validation never import the backend package or the runtime
driver; the backend package imports only the standard library and itself, and none of the modules that would give
it I/O, threads, a clock or randomness. The graph is read from the source with `ast`; nothing is imported or run.
Software evidence only.
"""
import ast
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "kritva_motion"
FORBIDDEN_IN_BACKEND = {"socket", "ssl", "http", "urllib", "subprocess", "threading", "multiprocessing", "asyncio", "sqlite3",
                        "shelve", "time", "datetime", "random", "secrets", "os", "pathlib", "io", "tempfile", "shutil", "logging",
                        "signal", "select", "selectors", "ctypes"}


def imports(path):
    """Fully dotted module names imported by a source file (absolute and from-imports)."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise AssertionError(f"{path}: relative imports are not used in this package")
            names.append(node.module or "")
            names += [f"{node.module}.{a.name}" for a in node.names]
    return names


def sources(*parts):
    base = SRC.joinpath(*parts)
    return [base] if base.suffix == ".py" else sorted(base.rglob("*.py"))


class TestImportDirection(unittest.TestCase):
    def test_the_engine_the_stores_and_admission_never_import_backend_or_runtime(self):
        for rel in (("lifecycle",), ("stores",), ("admission.py",), ("config_validation.py",)):
            for path in sources(*rel):
                for name in imports(path):
                    with self.subTest(file=str(path.relative_to(SRC)), name=name):
                        self.assertFalse(name.startswith(("kritva_motion.backend", "kritva_motion.runtime")), name)

    def test_the_backend_package_imports_only_the_standard_library_and_itself(self):
        stdlib = sys.stdlib_module_names
        for path in sources("backend"):
            for name in imports(path):
                top = name.split(".")[0]
                with self.subTest(file=path.name, name=name):
                    self.assertTrue(top in stdlib or name == "kritva_motion.backend" or name.startswith("kritva_motion.backend."),
                                    f"{path.name} imports {name}")

    def test_the_backend_package_has_no_io_thread_clock_or_randomness_import(self):
        for path in sources("backend"):
            for name in imports(path):
                with self.subTest(file=path.name, name=name):
                    self.assertNotIn(name.split(".")[0], FORBIDDEN_IN_BACKEND)

    def test_the_backend_package_does_not_import_the_engine_or_the_stores(self):
        for path in sources("backend"):
            for name in imports(path):
                with self.subTest(file=path.name, name=name):
                    self.assertFalse(name.startswith(("kritva_motion.lifecycle", "kritva_motion.stores", "kritva_motion.runtime",
                                                      "kritva_motion.admission", "kritva_motion.config_validation")), name)

    def test_the_check_sees_the_files(self):
        self.assertGreaterEqual(len(sources("backend")), 4)
        self.assertGreaterEqual(len(sources("lifecycle")), 3)


if __name__ == "__main__":
    unittest.main()
