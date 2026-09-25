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
