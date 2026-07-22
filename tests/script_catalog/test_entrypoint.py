from pathlib import Path

from script_catalog.entrypoint import (
    is_python_entrypoint,
    is_batch_entrypoint,
    is_mjs_entrypoint,
    is_entrypoint,
)


def test_python_file_with_main_guard_is_entrypoint(tmp_path):
    f = tmp_path / "runnable.py"
    f.write_text('print("hi")\n\nif __name__ == "__main__":\n    print("run")\n')
    assert is_python_entrypoint(f) is True


def test_python_helper_module_is_not_entrypoint(tmp_path):
    f = tmp_path / "helper.py"
    f.write_text("def helper():\n    return 1\n")
    assert is_python_entrypoint(f) is False


def test_python_file_with_single_quote_main_guard_is_entrypoint(tmp_path):
    f = tmp_path / "runnable2.py"
    f.write_text("if __name__ == '__main__':\n    pass\n")
    assert is_python_entrypoint(f) is True


def test_bat_file_is_always_entrypoint(tmp_path):
    f = tmp_path / "run.bat"
    f.write_text("@echo off\necho hi\n")
    assert is_batch_entrypoint(f) is True


def test_cmd_file_is_always_entrypoint(tmp_path):
    f = tmp_path / "run.cmd"
    f.write_text("@echo off\n")
    assert is_batch_entrypoint(f) is True


def test_mjs_with_top_level_main_call_is_entrypoint(tmp_path):
    f = tmp_path / "gen.mjs"
    f.write_text("async function main() {}\n\nawait main();\n")
    assert is_mjs_entrypoint(f) is True


def test_mjs_export_only_is_not_entrypoint(tmp_path):
    f = tmp_path / "lib.mjs"
    f.write_text("export function helper() { return 1; }\n")
    assert is_mjs_entrypoint(f) is False


def test_is_entrypoint_dispatches_by_extension(tmp_path):
    py_file = tmp_path / "a.py"
    py_file.write_text('if __name__ == "__main__":\n    pass\n')
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("not a script")

    assert is_entrypoint(py_file) is True
    assert is_entrypoint(txt_file) is False
