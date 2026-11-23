"""Verify strict upward import layering, acyclicity and module docstrings in bh_itbi."""

from __future__ import annotations

import ast
from collections import defaultdict
from graphlib import CycleError, TopologicalSorter
from importlib.util import resolve_name
from pathlib import Path

from bh_itbi.config import ROOT

PACKAGE_DIR = ROOT / "bh_itbi"

# Layer order from top (0) to bottom (10). A module may import only from layers
# with a lower or equal rank, and the full module dependency graph must be acyclic.
LAYER_RANK: dict[str, int] = {
    "bh_itbi": 0,
    "bh_itbi.config": 0,
    "bh_itbi.theme": 1,
    "bh_itbi.formatting": 1,
    "bh_itbi.text": 2,
    "bh_itbi.data": 3,
    "bh_itbi.filters": 4,
    "bh_itbi.stats": 4,
    "bh_itbi.robust": 4,
    "bh_itbi.urls": 4,
    "bh_itbi.overview": 5,
    "bh_itbi.diagnostics": 5,
    "bh_itbi.cluster": 5,
    "bh_itbi.patterns": 5,
    "bh_itbi.models": 5,
    "bh_itbi.sensitivity": 5,
    "bh_itbi.audit_checks": 5,
    "bh_itbi.age": 5,
    "bh_itbi.views": 6,
    "bh_itbi.audit": 6,
    "bh_itbi.figures": 7,
    "bh_itbi.layout": 8,
    "bh_itbi.callbacks": 9,
    "bh_itbi.app": 10,
}


def module_name_for_path(path: Path) -> str:
    """Convert a file path under ``bh_itbi/`` into its dotted Python module name."""
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def layer_key(module_name: str) -> str:
    """Map ``bh_itbi.<subpackage>.<leaf>`` to its top-level layer key."""
    parts = module_name.split(".")
    return ".".join(parts[:2])


def parse_internal_imports(path: Path, known_modules: set[str]) -> set[str]:
    """Return every ``bh_itbi`` module imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_name = module_name_for_path(path)
    package = module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "bh_itbi" or alias.name.startswith("bh_itbi."):
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.update(import_from_targets(node, package, known_modules))
    return imports


def import_from_targets(
    node: ast.ImportFrom, package: str, known_modules: set[str]
) -> set[str]:
    """Resolve absolute and relative imports, including imports of sibling modules."""
    parent = node.module or ""
    if node.level:
        parent = resolve_name("." * node.level + parent, package)
    if parent != "bh_itbi" and not parent.startswith("bh_itbi."):
        return set()
    return {
        candidate if candidate in known_modules else parent
        for alias in node.names
        for candidate in (f"{parent}.{alias.name}",)
    }


def test_import_layering_and_no_cycles() -> None:
    files = sorted(PACKAGE_DIR.rglob("*.py"))
    modules = {module_name_for_path(path): path for path in files}
    known_modules = set(modules)

    graph: dict[str, set[str]] = {}
    violations: list[str] = []

    for mod_name, path in modules.items():
        source_layer = layer_key(mod_name)
        assert source_layer in LAYER_RANK, f"Unregistered module layer: {source_layer}"
        source_rank = LAYER_RANK[source_layer]
        imported = parse_internal_imports(path, known_modules)
        graph[mod_name] = imported

        for target in sorted(imported):
            target_layer = layer_key(target)
            assert target_layer in LAYER_RANK, f"Unregistered target layer: {target_layer}"
            target_rank = LAYER_RANK[target_layer]
            if target_rank > source_rank:
                violations.append(
                    f"{mod_name} (layer {source_rank}) imports {target} (layer {target_rank})"
                )

    assert not violations, "Layering violations:\n  " + "\n  ".join(violations)

    try:
        list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise AssertionError(f"Import cycle detected in bh_itbi: {exc}") from exc


def test_every_module_starts_with_a_one_sentence_docstring() -> None:
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstring = ast.get_docstring(tree)
        assert docstring, f"Missing module docstring in {path.relative_to(ROOT)}"
        lines = [line.strip() for line in docstring.strip().splitlines() if line.strip()]
        assert len(lines) == 1, (
            f"Module docstring in {path.relative_to(ROOT)} must be a single sentence, "
            f"got {len(lines)} lines"
        )


def test_top_level_function_names_are_unique_across_modules() -> None:
    definitions: dict[str, set[str]] = defaultdict(set)
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions[node.name].add(str(path.relative_to(ROOT)))

    duplicates = [
        f"{name}: {', '.join(sorted(paths))}"
        for name, paths in sorted(definitions.items())
        if len(paths) > 1
    ]
    assert not duplicates, "Duplicate top-level function names:\n  " + "\n  ".join(duplicates)


def test_functions_fit_within_sixty_lines() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1
                if length > 60:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno} {node.name} ({length} lines)"
                    )
    assert not violations, "Functions over 60 lines:\n  " + "\n  ".join(violations)


def test_serving_cannot_reach_the_audit_modules() -> None:
    paths = [*sorted(PACKAGE_DIR.rglob("*.py")), ROOT / "wsgi.py"]
    modules = {module_name_for_path(path): path for path in paths}
    graph = {name: parse_internal_imports(path, set(modules)) for name, path in modules.items()}
    audit = {"bh_itbi.robust", "bh_itbi.sensitivity", "bh_itbi.audit_checks", "bh_itbi.audit"}
    serving_layers = {
        "bh_itbi.app",
        "bh_itbi.callbacks",
        "bh_itbi.layout",
        "bh_itbi.figures",
        "bh_itbi.views",
        "wsgi",
    }
    for module in modules:
        if layer_key(module) not in serving_layers:
            continue
        visited: set[str] = set()
        pending = [module]
        while pending:
            dependency = pending.pop()
            if dependency not in visited:
                visited.add(dependency)
                pending.extend(graph.get(dependency, ()))
        assert visited.isdisjoint(audit), (module, sorted(visited & audit))
