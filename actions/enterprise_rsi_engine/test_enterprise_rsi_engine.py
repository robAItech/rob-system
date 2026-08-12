import pytest
from fastapi.testclient import TestClient
from actions.enterprise_rsi_engine.main import app
from actions.enterprise_rsi_engine.enterprise_rsi_engine import RSIAnalyzer, RSIValidator

client = TestClient(app)


def test_analyzer_success():
    """Test that analyzer finds functions correctly."""
    analyzer = RSIAnalyzer()
    code = """
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""
    targets = analyzer.find_optimization_targets(code)
    assert len(targets) == 2
    assert targets[0].function_name == "add"
    assert targets[1].function_name == "multiply"
    assert all(0 <= t.risk_score <= 1 for t in targets)


def test_validator_success():
    """Test that validator confirms behavioral equivalence."""
    validator = RSIValidator()
    original = """
def add(a, b):
    return a + b
"""
    optimized = """
def add(a, b):
    return b + a
"""
    result = validator.verify_behavioral_equivalence(
        original, optimized, "add", [{"a": 1, "b": 2}, {"a": 10, "b": 20}]
    )
    assert result is True


def test_validator_fail():
    """Test that validator detects behavioral differences."""
    validator = RSIValidator()
    original = """
def add(a, b):
    return a + b
"""
    optimized = """
def add(a, b):
    return a - b
"""
    result = validator.verify_behavioral_equivalence(
        original, optimized, "add", [{"a": 1, "b": 2}]
    )
    assert result is False


def test_api_analyze():
    """Test the analyze API endpoint."""
    response = client.post(
        "/rsi/analyze",
        json={"module_code": "def foo():\n    return 1\n\ndef bar():\n    return 2\n"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["function_name"] == "foo"
    assert data[1]["function_name"] == "bar"


def test_api_validate():
    """Test the validate API endpoint."""
    response = client.post(
        "/rsi/validate",
        json={
            "original_func": "def add(a, b):\n    return a + b\n",
            "optimized_func": "def add(a, b):\n    return b + a\n",
            "func_name": "add",
            "test_args": [{"a": 1, "b": 2}, {"a": 5, "b": 10}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["equivalent"] is True


def test_api_validate_fail():
    """Test the validate API endpoint with non-equivalent functions."""
    response = client.post(
        "/rsi/validate",
        json={
            "original_func": "def add(a, b):\n    return a + b\n",
            "optimized_func": "def add(a, b):\n    return a - b\n",
            "func_name": "add",
            "test_args": [{"a": 1, "b": 2}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["equivalent"] is False


def test_analyzer_empty():
    """Test analyzer with no functions."""
    analyzer = RSIAnalyzer()
    targets = analyzer.find_optimization_targets("x = 5\ny = 10\n")
    assert len(targets) == 0