"""test_report_builder_uses_string_ops.py — pinning test (Task C).

Preveri, da report_builder uporablja konsolidiran actions.string_ops, ne več
zastarelega actions.slugify. Test-Locked.
"""
import inspect

from actions.report_builder import report_builder as rb

_SRC = inspect.getsource(rb)


def test_report_builder_ne_uporablja_slugify():
    assert "slugify" not in _SRC


def test_report_builder_uporablja_string_ops():
    assert "actions.string_ops" in _SRC
