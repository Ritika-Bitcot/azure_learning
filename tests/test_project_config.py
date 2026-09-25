import json
import re
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_host_json_leaves_routing_to_fastapi():
    host = json.loads((ROOT / "host.json").read_text())
    assert host["extensions"]["http"]["routePrefix"] == ""


def test_funcignore_keeps_dev_files_out_of_the_deployment():
    ignored = set((ROOT / ".funcignore").read_text().split())
    assert {".venv", "tests", "docs", "infra", "requirements-dev.txt", "local.settings.json"} <= ignored


def test_local_settings_template_has_empty_cosmos_settings():
    values = json.loads((ROOT / "local.settings.example.json").read_text())["Values"]
    assert values["FUNCTIONS_WORKER_RUNTIME"] == "python"
    assert values["AzureWebJobsStorage"] == ""
    assert values["COSMOS_ENDPOINT"] == "" and values["COSMOS_KEY"] == ""


def test_runtime_dependencies_are_pinned():
    lines = [
        line for line in (ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines and all("==" in line for line in lines)


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, version = line.split("==")
            pins[_normalise(name)] = version.strip()
    return pins


def _installed_runtime_tree(roots: list[str]) -> dict[str, str]:
    """Every installed distribution reachable from the direct runtime deps."""
    tree, todo = {}, list(roots)
    while todo:
        name = _normalise(todo.pop())
        if name in tree:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # requirement gated by a marker that does not apply here
        tree[name] = dist.version
        for requirement in dist.requires or []:
            if "extra ==" not in requirement:
                todo.append(re.match(r"[A-Za-z0-9._-]+", requirement).group(0))
    return tree


def test_whole_runtime_dependency_tree_is_pinned_to_the_tested_versions():
    # The remote build on deploy day must install exactly what the tests ran against.
    pins = _pins()
    assert _installed_runtime_tree(list(pins)) == pins


def test_repo_gitignore_keeps_azurite_and_pytest_cache_entries_separate():
    lines = (ROOT.parent / ".gitignore").read_text().splitlines()
    assert "AzuriteConfig" in lines
    assert ".pytest_cache/" in lines
