import pytest
from pathlib import Path
from core.registry import CompanyRegistry


@pytest.fixture
def registry(tmp_path):
    yaml_content = """
companies:
  AMC:
    company_code: "1000"
    source_type: sap
    bronze_paths:
      gl: "01_Bronze_Raw/gl/amc"
      sales: "01_Bronze_Raw/sales/amc"
  GA:
    company_code: "2000"
    source_type: sap
    bronze_paths:
      gl: "01_Bronze_Raw/gl/ga"
"""
    config_file = tmp_path / "company_registry.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")
    return CompanyRegistry(config_file, project_root=tmp_path)


def test_get_returns_company_dict(registry):
    amc = registry.get("AMC")
    assert amc["company_code"] == "1000"
    assert amc["source_type"] == "sap"


def test_get_bronze_path_resolves_to_absolute(registry, tmp_path):
    amc = registry.get("AMC")
    gl_path = amc["bronze_paths"]["gl"]
    assert gl_path.is_absolute()
    assert gl_path == tmp_path / "01_Bronze_Raw" / "gl" / "amc"


def test_get_unknown_company_raises(registry):
    with pytest.raises(KeyError, match="Unknown company"):
        registry.get("UNKNOWN")


def test_all_companies_returns_names(registry):
    names = registry.all_companies()
    assert "AMC" in names
    assert "GA" in names
    assert len(names) == 2
