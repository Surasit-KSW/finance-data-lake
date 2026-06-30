"""
tests/test_orchestrator.py — Unit tests for orchestrator.py

Uses mocked ETL classes so no real ETL runs happen.
Tests cover: run_domain, run_silver_for_company, print_summary, and main() arg routing.
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# ── Ensure orchestrator is importable from project root ──────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
PIPELINES_DIR = PROJECT_ROOT / "04_Data_Pipelines"
if str(PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINES_DIR))


# ── Shared ETL mock return value factory ─────────────────────────────────────

def _etl_result(company_code="1000", domain="gl", rows_in=100, rows_out=100,
                warnings=None, status="success"):
    return {
        "company_code": company_code,
        "domain": domain,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "warnings": warnings or [],
        "status": status,
    }


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_etl_class_mock(domain, rows_out=100, rows_in=100, status="success"):
    """Create a MagicMock that behaves like an ETL class."""
    MockCls = MagicMock()
    MockCls.return_value.run.return_value = _etl_result(
        domain=domain, rows_in=rows_in, rows_out=rows_out, status=status
    )
    return MockCls


@pytest.fixture
def mock_etl_success():
    """
    Patch orchestrator.ETL_CLASSES dict with mock classes returning success results.
    This is the correct approach since run_domain/run_silver_for_company use
    ETL_CLASSES (the dict) rather than the module-level name bindings.
    """
    import orchestrator
    mocks = {
        "gl":         _make_etl_class_mock("gl"),
        "sales":      _make_etl_class_mock("sales"),
        "production": _make_etl_class_mock("production"),
        "ar":         _make_etl_class_mock("ar"),
    }
    with patch.dict(orchestrator.ETL_CLASSES, mocks):
        yield mocks


@pytest.fixture
def mock_etl_failure():
    """Patch orchestrator.ETL_CLASSES with mock classes returning failed results."""
    import orchestrator
    mocks = {
        "gl":         _make_etl_class_mock("gl",         rows_in=0, rows_out=0, status="failed"),
        "sales":      _make_etl_class_mock("sales",      rows_in=0, rows_out=0, status="failed"),
        "production": _make_etl_class_mock("production", rows_in=0, rows_out=0, status="failed"),
        "ar":         _make_etl_class_mock("ar",         rows_in=0, rows_out=0, status="failed"),
    }
    with patch.dict(orchestrator.ETL_CLASSES, mocks):
        yield mocks


@pytest.fixture
def mock_subprocess_success():
    """Patch subprocess.run to always return returncode=0 (used for gold/init-db)."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("orchestrator.subprocess.run", return_value=mock_result) as mock_run:
        yield mock_run


@pytest.fixture
def mock_subprocess_failure():
    """Patch subprocess.run to always return returncode=1 (failure)."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("orchestrator.subprocess.run", return_value=mock_result) as mock_run:
        yield mock_run


# ── Tests: run_script (subprocess path — still used for gold + init-db) ──────

class TestRunScript:
    def test_returns_true_on_success(self, mock_subprocess_success):
        import orchestrator
        result = orchestrator.run_script(Path("some_script.py"), label="test")
        assert result is True

    def test_returns_false_on_failure(self, mock_subprocess_failure):
        import orchestrator
        result = orchestrator.run_script(Path("some_script.py"), label="test")
        assert result is False

    def test_passes_extra_args_to_subprocess(self, mock_subprocess_success):
        import orchestrator
        script = Path("some_script.py")
        orchestrator.run_script(script, extra_args=["--company", "AMC"], label="test")
        call_args = mock_subprocess_success.call_args
        cmd = call_args[0][0]
        assert "--company" in cmd
        assert "AMC" in cmd

    def test_uses_label_in_output(self, mock_subprocess_success, capsys):
        import orchestrator
        orchestrator.run_script(Path("some_script.py"), label="MY_LABEL")
        captured = capsys.readouterr()
        assert "MY_LABEL" in captured.out

    def test_defaults_label_to_script_name(self, mock_subprocess_success, capsys):
        import orchestrator
        orchestrator.run_script(Path("my_etl_script.py"))
        captured = capsys.readouterr()
        assert "my_etl_script.py" in captured.out


# ── Tests: run_domain ─────────────────────────────────────────────────────────

class TestRunDomain:
    """
    run_domain uses ETL_CLASSES dict (built at module load time).
    Patch orchestrator.ETL_CLASSES to replace the class, not just the name binding.
    """

    def _make_mock_etl(self, rows_out=500, status="success", domain="gl"):
        MockCls = MagicMock()
        MockCls.return_value.run.return_value = _etl_result(
            domain=domain, rows_out=rows_out, status=status
        )
        return MockCls

    def test_returns_tuple_with_result_dict(self):
        import orchestrator
        MockGL = self._make_mock_etl(rows_out=500, domain="gl")
        with patch.dict(orchestrator.ETL_CLASSES, {"gl": MockGL}):
            co_name, domain, result, elapsed = orchestrator.run_domain(
                "AMC", "gl",
                silver_path=Path("/fake/silver"),
                bronze_base=Path("/fake/bronze"),
                year=2026,
            )
        assert co_name == "AMC"
        assert domain == "gl"
        assert result["rows_out"] == 500
        assert result["status"] == "success"
        assert elapsed >= 0

    def test_gl_etl_receives_correct_kwargs(self):
        import orchestrator
        MockGL = self._make_mock_etl()
        with patch.dict(orchestrator.ETL_CLASSES, {"gl": MockGL}):
            orchestrator.run_domain(
                "AMC", "gl",
                silver_path=Path("/silver"),
                bronze_base=Path("/bronze/gl"),
                year=2026,
            )
        _, kwargs = MockGL.call_args
        assert kwargs["bronze_gl_path"] == Path("/bronze/gl")
        assert kwargs["silver_path"] == Path("/silver")
        assert kwargs["year"] == 2026

    def test_ar_etl_does_not_receive_year(self):
        """ARTransformETL does not accept year parameter."""
        import orchestrator
        MockAR = self._make_mock_etl(domain="ar")
        with patch.dict(orchestrator.ETL_CLASSES, {"ar": MockAR}):
            orchestrator.run_domain(
                "AMC", "ar",
                silver_path=Path("/silver"),
                bronze_base=Path("/bronze/ar"),
                year=2026,
            )
        _, kwargs = MockAR.call_args
        assert "year" not in kwargs
        assert kwargs["bronze_ar_path"] == Path("/bronze/ar")

    def test_sales_etl_receives_bronze_sales_path(self):
        import orchestrator
        MockSales = self._make_mock_etl(domain="sales")
        with patch.dict(orchestrator.ETL_CLASSES, {"sales": MockSales}):
            orchestrator.run_domain(
                "AMC", "sales",
                silver_path=Path("/silver"),
                bronze_base=Path("/bronze/sales"),
            )
        _, kwargs = MockSales.call_args
        assert "bronze_sales_path" in kwargs

    def test_production_etl_receives_bronze_prod_path(self):
        import orchestrator
        MockProd = self._make_mock_etl(domain="production")
        with patch.dict(orchestrator.ETL_CLASSES, {"production": MockProd}):
            orchestrator.run_domain(
                "AMC", "production",
                silver_path=Path("/silver"),
                bronze_base=Path("/bronze/prod"),
                year=2025,
            )
        _, kwargs = MockProd.call_args
        assert "bronze_prod_path" in kwargs
        assert kwargs["year"] == 2025


# ── Tests: run_silver_for_company ─────────────────────────────────────────────

class TestRunSilverForCompany:
    def test_returns_empty_list_for_unknown_company(self, capsys):
        import orchestrator
        results = orchestrator.run_silver_for_company("UNKNOWN_CO")
        assert results == []
        captured = capsys.readouterr()
        assert "UNKNOWN_CO" in captured.out

    def test_runs_gl_domain_for_amc(self, mock_etl_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("AMC", domain="gl")
        assert len(results) == 1
        r = results[0]
        assert r["company"] == "AMC"
        assert r["domain"] == "gl"
        assert r["status"] == "success"

    def test_runs_all_domains_for_amc_when_no_domain_specified(self, mock_etl_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("AMC")
        # AMC has gl, sales, production, ar
        assert len(results) == 4
        domains_run = [r["domain"] for r in results]
        assert "gl" in domains_run
        assert "sales" in domains_run
        assert "production" in domains_run
        assert "ar" in domains_run

    def test_ga_only_runs_available_domains(self, mock_etl_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("GA")
        # GA has gl and sales only
        assert len(results) == 2
        domains_run = [r["domain"] for r in results]
        assert "gl" in domains_run
        assert "sales" in domains_run
        assert "production" not in domains_run

    def test_passes_year_to_run_domain(self, mock_etl_success):
        import orchestrator
        with patch("orchestrator.run_domain") as mock_run_domain:
            mock_run_domain.return_value = ("AMC", "gl", _etl_result(), 0.5)
            orchestrator.run_silver_for_company("AMC", domain="gl", year=2026)
        _, kwargs = mock_run_domain.call_args
        assert kwargs.get("year") == 2026

    def test_no_year_when_not_provided(self, mock_etl_success):
        import orchestrator
        with patch("orchestrator.run_domain") as mock_run_domain:
            mock_run_domain.return_value = ("AMC", "gl", _etl_result(), 0.5)
            orchestrator.run_silver_for_company("AMC", domain="gl")
        _, kwargs = mock_run_domain.call_args
        assert kwargs.get("year") is None

    def test_result_has_failed_status_when_etl_fails(self, mock_etl_failure):
        import orchestrator
        results = orchestrator.run_silver_for_company("AMC", domain="gl")
        assert len(results) == 1
        assert results[0]["status"] == "failed"

    def test_stc_only_has_gl(self, mock_etl_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("STC")
        assert len(results) == 1
        assert results[0]["domain"] == "gl"

    def test_skips_domain_not_in_etl_classes(self, mock_etl_success, capsys):
        """If company registry has a domain with no ETL class, skip it gracefully."""
        import orchestrator
        fake_company = {
            "company_code": "9999",
            "source_type": "sap",
            "bronze_paths": {
                "gl": Path("/fake/gl"),
                "unknown_domain": Path("/fake/x"),
            },
        }
        with patch.object(orchestrator.REGISTRY, "get", return_value=fake_company):
            results = orchestrator.run_silver_for_company("TESTCO")
        # Only gl should run (unknown_domain has no ETL class)
        assert len(results) == 1
        captured = capsys.readouterr()
        assert "unknown_domain" in captured.out

    def test_progress_output_success_format(self, mock_etl_success, capsys):
        """Verify ✓ symbol appears for successful domain."""
        import orchestrator
        orchestrator.run_silver_for_company("AMC", domain="gl")
        captured = capsys.readouterr()
        assert "✓" in captured.out

    def test_progress_output_skipped_format(self, capsys):
        """Verify skipped message appears when rows_out == 0 and status == skipped."""
        import orchestrator
        MockGL = _make_etl_class_mock("gl", rows_in=0, rows_out=0, status="skipped")
        with patch.dict(orchestrator.ETL_CLASSES, {"gl": MockGL}):
            orchestrator.run_silver_for_company("AMC", domain="gl")
        captured = capsys.readouterr()
        assert "skipped" in captured.out

    def test_exception_in_run_domain_returns_failed(self, capsys):
        """run_domain raising an exception → result with status=failed, no crash."""
        import orchestrator
        with patch("orchestrator.run_domain", side_effect=RuntimeError("boom")):
            results = orchestrator.run_silver_for_company("AMC", domain="gl")
        assert results[0]["status"] == "failed"
        captured = capsys.readouterr()
        assert "exception" in captured.out.lower() or "boom" in captured.out


# ── Tests: print_summary ──────────────────────────────────────────────────────

class TestPrintSummary:
    def test_shows_all_passed(self, capsys):
        import orchestrator
        results = [
            {"company": "AMC", "domain": "gl", "status": "success", "rows_out": 100, "elapsed": 1.0},
            {"company": "AMC", "domain": "sales", "status": "success", "rows_out": 200, "elapsed": 1.5},
            {"company": "AMC", "domain": "production", "status": "success", "rows_out": 300, "elapsed": 2.0},
        ]
        orchestrator.print_summary(results)
        captured = capsys.readouterr()
        assert "3/3" in captured.out

    def test_shows_partial_failures(self, capsys):
        import orchestrator
        results = [
            {"company": "AMC", "domain": "gl", "status": "success", "rows_out": 100, "elapsed": 1.0},
            {"company": "AMC", "domain": "sales", "status": "failed", "rows_out": 0, "elapsed": 0.5},
            {"company": "AMC", "domain": "ar", "status": "success", "rows_out": 50, "elapsed": 0.8},
        ]
        orchestrator.print_summary(results)
        captured = capsys.readouterr()
        assert "2/3" in captured.out

    def test_shows_skipped_count(self, capsys):
        import orchestrator
        results = [
            {"company": "AMC", "domain": "gl", "status": "success", "rows_out": 100, "elapsed": 1.0},
            {"company": "GA",  "domain": "gl", "status": "skipped", "rows_out": 0,   "elapsed": 0.1},
        ]
        orchestrator.print_summary(results)
        captured = capsys.readouterr()
        assert "1" in captured.out  # 1 skipped

    def test_handles_empty_results(self, capsys):
        import orchestrator
        orchestrator.print_summary([])
        captured = capsys.readouterr()
        assert "0/0" in captured.out

    def test_old_tuple_format_still_works(self, capsys):
        """Backward compat: gold/init-db append (label, bool) tuples."""
        import orchestrator
        results = [("gold_gl_summary", True), ("init-db", True)]
        orchestrator.print_summary(results)
        captured = capsys.readouterr()
        assert "2/2" in captured.out


# ── Tests: main() CLI routing ─────────────────────────────────────────────────

class TestMainArgRouting:
    """Tests that main() routes args correctly by mocking run_silver_for_company and run_script."""

    def _run_main(self, args_list, etl_mocks=None, subprocess_mock=None):
        """Run orchestrator.main() with patched sys.argv."""
        with patch("sys.argv", ["orchestrator.py"] + args_list):
            import orchestrator
            orchestrator.main()

    def test_no_args_prints_help(self, capsys):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py"]):
            orchestrator.main()
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "orchestrator" in captured.out.lower()

    def test_init_db_calls_run_script_once(self, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--init-db"]):
            orchestrator.main()
        # Should call subprocess.run exactly once (for init_duckdb.py)
        assert mock_subprocess_success.call_count == 1
        cmd = mock_subprocess_success.call_args[0][0]
        assert "init_duckdb.py" in " ".join(str(c) for c in cmd)

    def test_company_layer_silver_runs_all_domains(self, mock_etl_success, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--layer", "silver"]):
            orchestrator.main()
        # AMC has 4 domains → 4 ETL class .run() calls
        total_calls = sum(
            mocked.return_value.run.call_count
            for mocked in mock_etl_success.values()
        )
        assert total_calls == 4

    def test_company_domain_gl_runs_one_domain(self, mock_etl_success, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--domain", "gl"]):
            orchestrator.main()
        assert mock_etl_success["gl"].return_value.run.call_count == 1
        assert mock_etl_success["sales"].return_value.run.call_count == 0

    def test_domain_only_runs_all_companies(self, mock_etl_success, mock_subprocess_success):
        """--domain gl without --company should run gl for all companies."""
        import orchestrator
        all_companies = orchestrator.REGISTRY.all_companies()
        with patch("sys.argv", ["orchestrator.py", "--domain", "gl", "--layer", "silver"]):
            orchestrator.main()
        # Every company has gl
        assert mock_etl_success["gl"].return_value.run.call_count == len(all_companies)

    def test_all_flag_runs_silver_gold_init(self, mock_etl_success, mock_subprocess_success):
        import orchestrator
        all_companies = orchestrator.REGISTRY.all_companies()
        total_domains = sum(
            len(orchestrator.REGISTRY.get(c)["bronze_paths"])
            for c in all_companies
        )
        gold_count = len(orchestrator.GOLD_SCRIPTS)
        init_count = 1
        expected_subprocess = gold_count + init_count

        with patch("sys.argv", ["orchestrator.py", "--all"]):
            orchestrator.main()

        # ETL direct calls == total_domains across all companies
        total_etl_calls = sum(
            mocked.return_value.run.call_count
            for mocked in mock_etl_success.values()
        )
        assert total_etl_calls == total_domains
        # subprocess only for gold + init-db
        assert mock_subprocess_success.call_count == expected_subprocess

    def test_include_gold_adds_gold_scripts(self, mock_etl_success, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--layer", "silver", "--include-gold"]):
            orchestrator.main()
        # ETL: 4 AMC domains
        total_etl = sum(m.return_value.run.call_count for m in mock_etl_success.values())
        assert total_etl == 4
        # subprocess: 1 gold script
        assert mock_subprocess_success.call_count == len(orchestrator.GOLD_SCRIPTS)

    def test_layer_gold_runs_only_gold(self, mock_etl_success, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--layer", "gold"]):
            orchestrator.main()
        # No ETL class calls
        total_etl = sum(m.return_value.run.call_count for m in mock_etl_success.values())
        assert total_etl == 0
        # subprocess for gold scripts only
        assert mock_subprocess_success.call_count == len(orchestrator.GOLD_SCRIPTS)
        cmd = mock_subprocess_success.call_args[0][0]
        assert "create_gold_summary.py" in " ".join(str(c) for c in cmd)

    def test_year_passed_through_to_etl(self, mock_etl_success, mock_subprocess_success):
        import orchestrator
        with patch("orchestrator.run_domain") as mock_run_domain:
            mock_run_domain.return_value = ("AMC", "gl", _etl_result(), 0.5)
            with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--domain", "gl", "--year", "2026"]):
                orchestrator.main()
        _, kwargs = mock_run_domain.call_args
        assert kwargs.get("year") == 2026
