"""Pytest test suite for ``actions.json_deep_merge.deep_merge``.

Verifies the documented merge semantics:

- ``dict`` vs ``dict``   -> recursive merge; ``b`` wins on key conflicts
- ``list`` vs ``list``   -> concatenation (``a`` items first)
- anything else          -> ``b`` wins
- inputs are never mutated; a brand-new structure is returned.
"""
from __future__ import annotations

try:  # repo layout: actions is an importable package
    from actions.json_deep_merge import deep_merge
except ImportError:  # pragma: no cover - flat-layout fallback
    from json_deep_merge import deep_merge


def test_dict_merge_recursive_and_b_wins():
    assert deep_merge({"a": 1, "b": [1]}, {"b": [2], "c": 3}) == {
        "a": 1,
        "b": [1, 2],
        "c": 3,
    }


def test_nested_dicts_merge_recursively():
    assert deep_merge({"x": {"y": 1}}, {"x": {"z": 2}}) == {"x": {"y": 1, "z": 2}}


def test_scalar_conflict_b_wins():
    assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_lists_are_concatenated_a_first():
    assert deep_merge({"a": [1, 2]}, {"a": [3, 4]}) == {"a": [1, 2, 3, 4]}


def test_top_level_lists_are_concatenated():
    assert deep_merge([1, 2], [3]) == [1, 2, 3]


def test_scalar_values_b_wins():
    assert deep_merge(1, 2) == 2
    assert deep_merge("left", "right") == "right"
    assert deep_merge(True, False) is False


def test_none_handling_b_wins():
    assert deep_merge({"a": 1}, {"a": None}) == {"a": None}
    assert deep_merge(None, {"a": 1}) == {"a": 1}
    assert deep_merge(None, None) is None


def test_mixed_types_b_wins():
    assert deep_merge({"a": [1]}, {"a": {"b": 2}}) == {"a": {"b": 2}}
    assert deep_merge({"a": 1}, {"a": [1]}) == {"a": [1]}


def test_keys_only_in_a_are_preserved():
    assert deep_merge({"a": 1, "b": 2}, {"c": 3}) == {"a": 1, "b": 2, "c": 3}


def test_empty_structures():
    assert deep_merge({}, {}) == {}
    assert deep_merge({}, {"a": 1}) == {"a": 1}
    assert deep_merge({"a": 1}, {}) == {"a": 1}
    assert deep_merge([], []) == []


def test_deeply_nested_merge():
    result = deep_merge(
        {"a": {"b": {"c": [1], "d": {"e": 1}}}},
        {"a": {"b": {"c": [2], "d": {"f": 2}}}},
    )
    assert result == {"a": {"b": {"c": [1, 2], "d": {"e": 1, "f": 2}}}}


def test_inputs_are_not_mutated():
    a = {"a": {"b": [1]}, "list": [1, 2]}
    b = {"a": {"c": 2}, "list": [3]}
    a_before = {"a": {"b": [1]}, "list": [1, 2]}
    b_before = {"a": {"c": 2}, "list": [3]}
    deep_merge(a, b)
    assert a == a_before
    assert b == b_before


def test_result_is_a_fresh_structure():
    a = {"a": [1]}
    b = {"a": [2]}
    result = deep_merge(a, b)
    assert result is not a
    assert result is not b
    assert result["a"] is not a["a"]
    assert result["a"] is not b["a"]
