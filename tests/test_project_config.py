import json
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
