import pytest
from fastapi.testclient import TestClient
from actions.rsi_engine.main import app
from actions.rsi_engine.rsi_engine import RSIAnalyzer

client = TestClient(app)

def test_analyzer_get_functions():
    code = "def calc(a, b):\n    return a + b\n"
    res = RSIAnalyzer.analyze_code(code)
    assert res.success is True
    assert len(res.functions) == 1
    assert res.functions[0].name == "calc"
    assert res.functions[0].args == ["a", "b"]

def test_analyzer_get_classes():
    code = "class Worker:\n    def do_work(self):\n        pass\n"
    res = RSIAnalyzer.analyze_code(code)
    assert res.success is True
    assert len(res.classes) == 1
    assert res.classes[0].name == "Worker"
    assert "do_work" in res.classes[0].methods

def test_analyzer_complexity_score():
    code = "def check(x):\n    if x > 0:\n        for i in range(x):\n            pass\n"
    res = RSIAnalyzer.analyze_code(code)
    assert res.success is True
    assert res.complexity_score == 2

def test_analyze_endpoint_with_code():
    response = client.post("/rsi/analyze", json={"module_code": "def foo(): pass"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["functions"]) == 1

def test_analyze_endpoint_with_file(tmp_path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("def bar(): return 42")
    response = client.post("/rsi/analyze", json={"target_module_path": str(test_file)})
    assert response.status_code == 200
    data = response.json()
    assert data["functions"][0]["name"] == "bar"

def test_analyze_missing_input():
    response = client.post("/rsi/analyze", json={})
    assert response.status_code == 400

def test_run_loop_endpoint_success(tmp_path):
    test_file = tmp_path / "target.py"
    test_file.write_text("def run(): pass")
    response = client.post("/rsi/run-loop", json={"target_module_path": str(test_file), "max_retries": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

def test_run_loop_endpoint_not_found():
    response = client.post("/rsi/run-loop", json={"target_module_path": "non_existent.py"})
    assert response.status_code == 404
