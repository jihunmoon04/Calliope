"""Redesign boundaries.

- The new packages (`calliope.facts`, `calliope.reasoning`) and the frozen legacy MVP never import
  each other.
- `calliope.facts` never imports `calliope.reasoning`.
- `calliope.reasoning` reaches the fact engine only through the package `calliope.facts` (its
  public names) and never imports python-chess (reasoning R0-D §3.3, §18.1).
"""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "calliope"
NEW_PACKAGES = ("facts", "reasoning")
LEGACY_MODULES = (
    "adapters",
    "application",
    "domain",
    "services",
    "composition",
    "contracts",
    "engine",
    "errors",
)


def _imported_modules(path: Path) -> set[str]:
    package = ".".join(path.relative_to(SRC.parent).with_suffix("").parts[:-1])
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                modules.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module:
                modules.add(node.module)
    return modules


def _imported_calliope_modules(path: Path) -> set[str]:
    package = ".".join(path.relative_to(SRC.parent).with_suffix("").parts[:-1])
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                modules.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module:
                modules.add(node.module)
    return {m for m in modules if m == "calliope" or m.startswith("calliope.")}


def _top(module: str) -> str | None:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else None


def _sources(top: str) -> list[Path]:
    target = SRC / top
    if target.is_dir():
        return sorted(target.rglob("*.py"))
    file = SRC / f"{top}.py"
    return [file] if file.exists() else []


def test_new_packages_do_not_import_legacy() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports {module}"
        for top in NEW_PACKAGES
        for path in _sources(top)
        for module in _imported_calliope_modules(path)
        if module == "calliope" or _top(module) in LEGACY_MODULES
    ]
    assert offenders == []


def test_legacy_does_not_import_new_packages() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports {module}"
        for top in LEGACY_MODULES
        for path in _sources(top)
        for module in _imported_calliope_modules(path)
        if _top(module) in NEW_PACKAGES
    ]
    assert offenders == []


def test_importing_the_package_loads_no_legacy_module() -> None:
    probe = (
        "import sys, calliope; print(sorted(m for m in sys.modules if m.startswith('calliope.')))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert loaded == "[]"


def test_legacy_facade_names_still_resolve() -> None:
    import calliope
    from calliope.contracts import AnalyzeMoveRequest
    from calliope.engine import CalliopeEngine

    assert calliope.AnalyzeMoveRequest is AnalyzeMoveRequest
    assert calliope.CalliopeEngine is CalliopeEngine
    assert set(calliope.__all__) <= set(dir(calliope))


def test_facts_does_not_import_reasoning() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports {module}"
        for path in _sources("facts")
        for module in _imported_calliope_modules(path)
        if _top(module) == "reasoning"
    ]
    assert offenders == []


def test_reasoning_uses_only_the_public_fact_engine_and_no_python_chess() -> None:
    offenders = []
    for path in _sources("reasoning"):
        for module in _imported_modules(path):
            python_chess = module.split(".")[0] == "chess"
            private_facts = _top(module) == "facts" and module != "calliope.facts"
            if python_chess or (module.startswith("calliope.") and private_facts):
                offenders.append(f"{path.relative_to(SRC.parent)} imports {module}")
    assert offenders == []
