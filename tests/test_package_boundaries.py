"""Redesign boundaries.

- `src/calliope/` holds only `__init__.py` and the redesign packages (`facts`, `reasoning`,
  `results`, `server`); the MVP is history at tag `legacy-final` (LR-D §4).
- `import calliope` loads no submodule, and no package imports the root package `calliope`.
- `calliope.facts` never imports `calliope.reasoning`; neither imports `calliope.results`.
- `calliope.reasoning` reaches the fact engine only through the package `calliope.facts` (its
  public names) and never imports python-chess (reasoning R0-D §3.3, §18.1).
- `calliope.results` reaches them only through the packages `calliope.reasoning` and
  `calliope.facts` (their public names) and never imports python-chess (AR-D G2).
- `calliope.server` (AS-D S2) reaches them through the packages `calliope.facts`,
  `calliope.reasoning` (and its storage module, R4's save and load) and `calliope.results`; it
  may use python-chess, being AR-D G8's caller. Nothing in facts, reasoning or results imports it.
"""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "calliope"
PACKAGES = ("facts", "reasoning", "results", "server")


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


def test_src_holds_only_the_redesign_packages() -> None:
    """LR-D §4: a module outside the redesign packages cannot appear unnoticed."""

    entries = {p.name for p in SRC.iterdir() if p.name != "__pycache__"}
    assert entries == {"__init__.py", *PACKAGES}


def test_no_package_imports_the_root_package() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports calliope"
        for top in PACKAGES
        for path in _sources(top)
        for module in _imported_calliope_modules(path)
        if module == "calliope"
    ]
    tools = SRC.parents[1] / "tools"
    offenders += [
        f"{path.relative_to(tools.parent)} imports calliope"
        for path in sorted(tools.rglob("*.py"))
        if "calliope" in _absolute_imports(path)
    ]
    assert offenders == []


def test_importing_the_package_loads_no_submodule() -> None:
    probe = (
        "import sys, calliope; print(sorted(m for m in sys.modules if m.startswith('calliope.')))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert loaded == "[]"


def test_facts_does_not_import_reasoning() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports {module}"
        for path in _sources("facts")
        for module in _imported_calliope_modules(path)
        if _top(module) == "reasoning"
    ]
    assert offenders == []


def test_nothing_below_results_imports_it() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports {module}"
        for top in ("facts", "reasoning")
        for path in _sources(top)
        for module in _imported_calliope_modules(path)
        if _top(module) == "results"
    ]
    assert offenders == []


def test_results_uses_only_public_names_and_no_python_chess() -> None:
    offenders = []
    for path in _sources("results"):
        for module in _imported_modules(path):
            python_chess = module.split(".")[0] == "chess"
            inner = module.startswith("calliope.") and _top(module) != "results"
            if python_chess or (inner and module not in ("calliope.facts", "calliope.reasoning")):
                offenders.append(f"{path.relative_to(SRC.parent)} imports {module}")
    assert offenders == []
    assert _sources("results")  # the scan sees the package


def test_reasoning_uses_only_the_public_fact_engine_and_no_python_chess() -> None:
    offenders = []
    for path in _sources("reasoning"):
        for module in _imported_modules(path):
            python_chess = module.split(".")[0] == "chess"
            private_facts = _top(module) == "facts" and module != "calliope.facts"
            if python_chess or (module.startswith("calliope.") and private_facts):
                offenders.append(f"{path.relative_to(SRC.parent)} imports {module}")
    assert offenders == []


def _absolute_imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            modules.add(node.module)
    return modules


SERVER_IMPORTS = (
    "calliope.facts",
    "calliope.reasoning",
    "calliope.reasoning.storage",
    "calliope.results",
)


def test_nothing_below_server_imports_it() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports {module}"
        for top in ("facts", "reasoning", "results")
        for path in _sources(top)
        for module in _imported_calliope_modules(path)
        if _top(module) == "server"
    ]
    assert offenders == []


def test_server_uses_only_public_names() -> None:
    offenders = [
        f"{path.relative_to(SRC.parent)} imports {module}"
        for path in _sources("server")
        for module in _imported_calliope_modules(path)
        if _top(module) != "server" and module not in SERVER_IMPORTS
    ]
    assert offenders == []
    assert _sources("server")  # the scan sees the package
