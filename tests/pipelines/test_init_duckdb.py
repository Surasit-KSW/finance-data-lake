"""
test_init_duckdb.py — Test init_duckdb.py view registration with new patterns
"""
import os
import pytest
from pathlib import Path


def test_views_dict_uses_new_patterns():
    """Test that VIEWS dict uses per-company file patterns"""
    # Import the init_duckdb module to check VIEWS dict
    spec_path = Path(__file__).resolve().parent.parent.parent / "04_Data_Pipelines" / "init_duckdb.py"
    assert spec_path.exists(), f"init_duckdb.py not found at {spec_path}"

    # Read the file and check for new patterns
    with open(spec_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Verify new patterns are present
    assert 'master_gl_*.parquet' in content, "v_gl should use master_gl_*.parquet pattern"
    assert 'master_sales_*.parquet' in content, "v_sales should use master_sales_*.parquet pattern"
    assert 'master_production_*.parquet' in content, "v_production should use master_production_*.parquet pattern"
    assert 'master_ar_*.parquet' in content, "v_ar should use master_ar_*.parquet pattern"

    # Verify old patterns are removed (or replaced)
    # The old Master_GL_*.parquet should be replaced with master_gl_*.parquet
    # Check that we're not using the old capitalized version in v_gl
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '"v_gl"' in line:
            # v_gl definition found, check if it uses the new pattern
            if 'master_gl_*.parquet' in line:
                break  # Found it, test passes
            else:
                # Look in next few lines
                found = False
                for j in range(i+1, min(i+3, len(lines))):
                    if 'master_gl_*.parquet' in lines[j]:
                        found = True
                        break
                assert found, f"v_gl should use lowercase master_gl_ pattern"
                break


def test_views_dict_no_year_views():
    """Test that YEAR_VIEWS dict is empty"""
    spec_path = Path(__file__).resolve().parent.parent.parent / "04_Data_Pipelines" / "init_duckdb.py"

    with open(spec_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check that YEAR_VIEWS is empty
    assert 'YEAR_VIEWS = {}' in content, "YEAR_VIEWS should be empty dict"

    # Verify old year-based views are not defined inline
    assert 'v_sales_2023' not in content or '"v_sales_2023"' not in content, \
        "Old year-based views should not be hardcoded in VIEWS dict"


def test_create_view_handles_glob_patterns():
    """Test that create_view function properly handles glob patterns with *"""
    spec_path = Path(__file__).resolve().parent.parent.parent / "04_Data_Pipelines" / "init_duckdb.py"

    with open(spec_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for the glob pattern detection logic
    assert 'if "*" in parquet_glob:' in content, \
        "create_view should check for * in pattern"

    assert 'glob_lib.glob(parquet_glob)' in content, \
        "create_view should use glob.glob for patterns with *"

    assert 'os.path.exists(parquet_glob)' in content, \
        "create_view should check os.path.exists for single files"


def test_views_dict_keys_are_correct():
    """Test that VIEWS dict has the expected view names"""
    spec_path = Path(__file__).resolve().parent.parent.parent / "04_Data_Pipelines" / "init_duckdb.py"

    with open(spec_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # These views must exist
    required_views = [
        'v_gl',
        'v_sales',
        'v_production',
        'v_ar',
        'v_gl_summary',
        'gold_revenue_monthly',
        'gold_gp_by_plant',
    ]

    for view_name in required_views:
        assert f'"{view_name}"' in content or f"'{view_name}'" in content, \
            f"View {view_name} should be defined in VIEWS dict"
