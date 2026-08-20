import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from actions.deployment_manager.deployment_manager import DeploymentManager

@pytest.fixture
def mock_env(tmp_path):
    # Priprava izoliranega testnega okolja (tmp_path prepreči uničenje pravega sistema)
    actions = tmp_path / "actions"
    actions.mkdir()
    (actions / "api_gateway").mkdir()
    (actions / "auth_vault").mkdir()
    
    gw_main = actions / "api_gateway" / "main.py"
    gw_main.write_text("ROUTES = [\n  ('old', '/api', 'http', False)\n]", encoding="utf-8")
    
    return tmp_path

@pytest.mark.asyncio
async def test_deployment_manager_logic(mock_env):
    mgr = DeploymentManager(base_dir=str(mock_env))
    
    # Preveri detekcijo storitev in dodeljevanje portov
    services = mgr.get_services()
    assert "api_gateway" in services
    assert services["api_gateway"] == 8000
    assert "auth_vault" in services
    
    # Preveri zapis docker-compose.yml
    compose_content = mgr.generate_docker_compose()
    assert "rob_api_gateway" in compose_content
    assert (mock_env / "docker-compose.yml").exists()

    # Preveri posodobitev Gatewaya
    success = mgr.update_gateway_routes()
    assert success is True
    updated_gw = (mock_env / "actions" / "api_gateway" / "main.py").read_text()
    assert "/api/auth_vault" in updated_gw
    assert "old" not in updated_gw

@pytest.mark.asyncio
async def test_get_services_excludes_artifacts_and_ci_only(tmp_path, monkeypatch):
    # Artefaktne mape (skrite / __) in CI-only moduli se NE smejo deployati.
    actions = tmp_path / "actions"
    actions.mkdir()
    (actions / "api_gateway").mkdir()
    (actions / "ci_only_demo").mkdir()       # CI-only (vidno prek monkeypatch)
    (actions / ".pytest_cache").mkdir()      # skrit artefakt
    (actions / "__pycache__").mkdir()        # Python meta-mapa

    monkeypatch.setattr(DeploymentManager, "CI_ONLY_MODULES", {"ci_only_demo"})

    mgr = DeploymentManager(base_dir=str(tmp_path))
    services = mgr.get_services()

    assert "api_gateway" in services
    assert "ci_only_demo" not in services
    assert ".pytest_cache" not in services
    assert "__pycache__" not in services


@pytest.mark.asyncio
async def test_deployment_subprocess_mock(mock_env):
    mgr = DeploymentManager(base_dir=str(mock_env))
    
    class MockProcess:
        returncode = 0
        async def wait(self): pass

    with patch('asyncio.create_subprocess_shell', return_value=MockProcess()) as mock_sub:
        code = await mgr.run_deployment()
        assert code == 0
        mock_sub.assert_called_once()
