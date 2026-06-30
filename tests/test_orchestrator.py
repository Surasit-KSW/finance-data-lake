"""
tests/test_orchestrator.py — Unit tests for orchestrator.py

Uses mocked subprocess.run so no real ETL runs happen.
Tests cover: run_script, run_silver_for_company, print_summary, and main() arg routing.
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import subprocess

# ── Ensure orchestrator is importable from project root ──────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
PIPELINES_DIR = PROJECT_ROOT / "04_Data_Pipelines"
if str(PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINES_DIR))


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_subprocess_success():
    """Patch subprocess.run to always return returncode=0 (success)."""
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


# ── Tests: run_script ─────────────────────────────────────────────────────────

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


# ── Tests: run_silver_for_company ─────────────────────────────────────────────

class TestRunSilverForCompany:
    def test_returns_empty_list_for_unknown_company(self, capsys):
        import orchestrator
        results = orchestrator.run_silver_for_company("UNKNOWN_CO")
        assert results == []
        captured = capsys.readouterr()
        assert "UNKNOWN_CO" in captured.out

    def test_runs_gl_domain_for_amc(self, mock_subprocess_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("AMC", domain="gl")
        assert len(results) == 1
        label, ok = results[0]
        assert "AMC" in label
        assert "gl" in label
        assert ok is True

    def test_runs_all_domains_for_amc_when_no_domain_specified(self, mock_subprocess_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("AMC")
        # AMC has gl, sales, production, ar
        assert len(results) == 4
        domains_run = [label.split("] ")[1] for label, _ in results]
        assert "gl" in domains_run
        assert "sales" in domains_run
        assert "production" in domains_run
        assert "ar" in domains_run

    def test_ga_only_runs_available_domains(self, mock_subprocess_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("GA")
        # GA has gl and sales only
        assert len(results) == 2
        domains_run = [label.split("] ")[1] for label, _ in results]
        assert "gl" in domains_run
        assert "sales" in domains_run
        assert "production" not in domains_run

    def test_passes_year_arg_when_provided(self, mock_subprocess_success):
        import orchestrator
        orchestrator.run_silver_for_company("AMC", domain="gl", year=2026)
        call_args = mock_subprocess_success.call_args
        cmd = call_args[0][0]
        assert "--year" in cmd
        assert "2026" in cmd

    def test_no_year_arg_when_not_provided(self, mock_subprocess_success):
        import orchestrator
        orchestrator.run_silver_for_company("AMC", domain="gl")
        call_args = mock_subprocess_success.call_args
        cmd = call_args[0][0]
        assert "--year" not in cmd

    def test_result_is_false_when_script_fails(self, mock_subprocess_failure):
        import orchestrator
        results = orchestrator.run_silver_for_company("AMC", domain="gl")
        assert len(results) == 1
        _, ok = results[0]
        assert ok is False

    def test_stc_only_has_gl(self, mock_subprocess_success):
        import orchestrator
        results = orchestrator.run_silver_for_company("STC")
        assert len(results) == 1
        label, _ = results[0]
        assert "gl" in label

    def test_skips_domain_not_in_domain_scripts(self, mock_subprocess_success, capsys):
        """If company registry has a domain with no ETL script, skip it gracefully."""
        import orchestrator
        # Temporarily add a domain that has no script
        import orchestrator as orch
        # Patch registry to return a company with a fake domain
        fake_company = {
            "company_code": "9999",
            "source_type": "sap",
            "bronze_paths": {"gl": Path("/fake/gl"), "unknown_domain": Path("/fake/x")},
        }
        with patch.object(orch.REGISTRY, "get", return_value=fake_company):
            results = orch.run_silver_for_company("TESTCO")
        # Only gl should run (unknown_domain has no script)
        assert len(results) == 1
        captured = capsys.readouterr()
        assert "unknown_domain" in captured.out or len(results) == 1


# ── Tests: print_summary ──────────────────────────────────────────────────────

class TestPrintSummary:
    def test_shows_all_passed(self, capsys):
        import orchestrator
        results = [("task1", True), ("task2", True), ("task3", True)]
        orchestrator.print_summary(results)
        captured = capsys.readouterr()
        assert "3/3" in captured.out

    def test_shows_partial_failures(self, capsys):
        import orchestrator
        results = [("task1", True), ("task2", False), ("task3", True)]
        orchestrator.print_summary(results)
        captured = capsys.readouterr()
        assert "2/3" in captured.out
        assert "1" in captured.out  # 1 error

    def test_shows_all_failed(self, capsys):
        import orchestrator
        results = [("task1", False), ("task2", False)]
        orchestrator.print_summary(results)
        captured = capsys.readouterr()
        assert "0/2" in captured.out

    def test_handles_empty_results(self, capsys):
        import orchestrator
        orchestrator.print_summary([])
        captured = capsys.readouterr()
        assert "0/0" in captured.out


# ── Tests: main() CLI routing ─────────────────────────────────────────────────

class TestMainArgRouting:
    """Tests that main() routes args correctly by mocking run_script."""

    def _run_main(self, args_list):
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

    def test_company_layer_silver_runs_all_domains(self, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--layer", "silver"]):
            orchestrator.main()
        # AMC has 4 domains → 4 subprocess calls
        assert mock_subprocess_success.call_count == 4

    def test_company_domain_gl_runs_one_domain(self, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--domain", "gl"]):
            orchestrator.main()
        assert mock_subprocess_success.call_count == 1
        cmd = mock_subprocess_success.call_args[0][0]
        assert "etl_gl.py" in " ".join(str(c) for c in cmd)

    def test_domain_only_runs_all_companies(self, mock_subprocess_success):
        """--domain gl without --company should run gl for all companies."""
        import orchestrator
        all_companies = orchestrator.REGISTRY.all_companies()
        with patch("sys.argv", ["orchestrator.py", "--domain", "gl", "--layer", "silver"]):
            orchestrator.main()
        # Every company has gl — so count == number of companies
        assert mock_subprocess_success.call_count == len(all_companies)

    def test_all_flag_runs_silver_gold_init(self, mock_subprocess_success):
        import orchestrator
        all_companies = orchestrator.REGISTRY.all_companies()
        # Count total domains across all companies + 1 gold + 1 init-db
        total_domains = sum(
            len(orchestrator.REGISTRY.get(c)["bronze_paths"])
            for c in all_companies
        )
        gold_count = len(orchestrator.GOLD_SCRIPTS)
        init_count = 1
        expected = total_domains + gold_count + init_count

        with patch("sys.argv", ["orchestrator.py", "--all"]):
            orchestrator.main()
        assert mock_subprocess_success.call_count == expected

    def test_include_gold_adds_gold_scripts(self, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--layer", "silver", "--include-gold"]):
            orchestrator.main()
        # 4 AMC domains + 1 gold
        assert mock_subprocess_success.call_count == 4 + len(orchestrator.GOLD_SCRIPTS)

    def test_layer_gold_runs_only_gold(self, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--layer", "gold"]):
            orchestrator.main()
        assert mock_subprocess_success.call_count == len(orchestrator.GOLD_SCRIPTS)
        cmd = mock_subprocess_success.call_args[0][0]
        assert "create_gold_summary.py" in " ".join(str(c) for c in cmd)

    def test_year_passed_through_to_etl(self, mock_subprocess_success):
        import orchestrator
        with patch("sys.argv", ["orchestrator.py", "--company", "AMC", "--domain", "gl", "--year", "2026"]):
            orchestrator.main()
        cmd = mock_subprocess_success.call_args[0][0]
        assert "--year" in cmd
        assert "2026" in cmd
