import json
import os
import subprocess
from pathlib import Path

import pytest

from app.repository import LIST_QUERY

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
SCRIPTS = ["deploy.sh", "teardown.sh", "smoke.sh"]


def test_index_policy_has_the_composite_index_the_list_query_needs():
    assert "ORDER BY c.created_at DESC, c.id DESC" in LIST_QUERY
    policy = json.loads((INFRA / "cosmos-index-policy.json").read_text())
    assert [
        {"path": "/created_at", "order": "descending"},
        {"path": "/id", "order": "descending"},
    ] in policy["compositeIndexes"]


@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_are_executable_and_parse(script):
    path = INFRA / script
    assert os.access(path, os.X_OK)
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_config_uses_the_agreed_names_and_region():
    config = (INFRA / "config.sh").read_text()
    for expected in (
        'LOCATION="eastus2"',
        'PYTHON_VERSION="3.11"',
        'RESOURCE_GROUP="rg-fastapi-crud-dev-eus2"',
        'STORAGE_ACCOUNT="stfastapicruddeveus2"',
        'COSMOS_ACCOUNT="cosmos-fastapi-crud-dev-eus2"',
        'FUNCTION_APP="func-fastapi-crud-dev-eus2"',
        'APP_INSIGHTS="appi-fastapi-crud-dev-eus2"',
        "COSMOS_THROUGHPUT=1000",
    ):
        assert expected in config


def test_deploy_never_lets_the_cli_create_its_own_app_insights():
    assert "--disable-app-insights" in (INFRA / "deploy.sh").read_text()


def _logical_lines(script: str) -> list[str]:
    return (INFRA / script).read_text().replace("\\\n", " ").splitlines()


@pytest.mark.parametrize("script", ["deploy.sh", "teardown.sh", "config.sh"])
def test_captured_az_output_is_always_tsv(script):
    # A user's `az config set core.output=...` must not change what the scripts compare against.
    captured = [line for line in _logical_lines(script) if "$(az " in line]
    assert captured
    for line in captured:
        assert "-o tsv" in line, line


def test_publish_runs_with_the_project_venv_python():
    publish = [line for line in _logical_lines("deploy.sh") if "functionapp publish" in line]
    assert publish and all('PATH="$ROOT/.venv/bin:$PATH"' in line for line in publish)


def test_host_lookup_handles_the_flex_consumption_response_shape():
    # az 2.90 returns Flex apps in raw ARM shape: the host is under properties.defaultHostName.
    lookups = [line for line in _logical_lines("deploy.sh") if "defaultHostName" in line]
    assert lookups
    for line in lookups:
        assert '"properties.defaultHostName || defaultHostName"' in line, line
