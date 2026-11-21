"""
Regression tests for the Feedback Ingestion Streamlit page (2_Feedback_Ingestion.py).

Uses streamlit.testing.v1.AppTest to execute the page against an isolated
temporary database (via PRODUCTSIGNAL_DB_PATH). These tests exist because the
module-level suite does not execute Streamlit pages and previously missed a
P0 AttributeError crash in this page.

Note: AppTest (Streamlit 1.67) cannot simulate file_uploader uploads, so
upload-driven paths are covered via unit tests of _TempCSVContext, which is
the single cleanup mechanism used by every page path.
"""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PAGE_PATH = PROJECT_ROOT / "src" / "productsignal" / "app" / "pages" / "2_Feedback_Ingestion.py"
BUNDLED_DATASET = PROJECT_ROOT / "data" / "raw" / "customer_support_tickets.csv"


class FakeProduct:
    """Minimal stand-in for an active ProductContext record."""

    product_id = 1
    name = "TestSaaS"
    product_type = "service_based"
    category = "saas"
    vibe_key = "saas"


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """Redirect the page's database to an isolated temporary file."""
    db_path = tmp_path / "page_test.db"
    monkeypatch.setenv("PRODUCTSIGNAL_DB_PATH", str(db_path))
    yield db_path


@pytest.fixture
def page_module():
    """Load the ingestion page module without executing main()."""
    spec = importlib.util.spec_from_file_location("ingestion_page_under_test", PAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(PAGE_PATH), default_timeout=60)


def _shrink_dataset(monkeypatch):
    """Speed up full-page runs: preview only the first 20 rows of any CSV."""
    from productsignal.ingestion import csv_ingestion

    original_load = csv_ingestion.load_csv

    def fast_load(file_path):
        return original_load(file_path).head(20)

    monkeypatch.setattr(csv_ingestion, "load_csv", fast_load)


class TestPageLoads:
    """AppTest scenarios: the page must load without raising."""

    def test_no_active_product(self, isolated_db):
        """Page loads safely with no active product selected."""
        at = _make_app()
        at.run()
        assert not at.exception, f"Page raised: {[e.value for e in at.exception]}"
        assert any("No active project" in w.value for w in at.warning)

    def test_active_product(self, isolated_db, monkeypatch):
        """Page loads safely with an active product (regression for the P0 AttributeError)."""
        _shrink_dataset(monkeypatch)
        at = _make_app()
        at.session_state["active_product"] = FakeProduct()
        at.run()
        assert not at.exception, f"Page raised: {[e.value for e in at.exception]}"
        assert not any("temp_csv_path" in str(e.value) for e in at.exception)

    def test_active_product_rerun_stable(self, isolated_db, monkeypatch):
        """Page remains stable across reruns with an active product."""
        _shrink_dataset(monkeypatch)
        at = _make_app()
        at.session_state["active_product"] = FakeProduct()
        at.run()
        assert not at.exception
        at.run()
        assert not at.exception, f"Rerun raised: {[e.value for e in at.exception]}"

    def test_active_product_no_uploaded_file(self, isolated_db, monkeypatch):
        """With the default dataset unchecked and nothing uploaded, the page shows guidance."""
        _shrink_dataset(monkeypatch)
        at = _make_app()
        at.session_state["active_product"] = FakeProduct()
        at.run()
        assert not at.exception

        # Uncheck "Use default Kaggle dataset" -> file_path becomes None
        checkbox = at.checkbox[0]
        checkbox.uncheck().run()
        assert not at.exception, f"Rerun raised: {[e.value for e in at.exception]}"
        assert any("select or upload a CSV" in i.value for i in at.info)

    def test_load_failure_path_shows_error_and_no_crash(self, isolated_db, monkeypatch):
        """CSV load exceptions surface as a friendly error, trigger cleanup, and do not crash."""
        from productsignal.ingestion import csv_ingestion

        def failing_load(file_path):
            raise RuntimeError("simulated parse failure")

        monkeypatch.setattr(csv_ingestion, "load_csv", failing_load)
        at = _make_app()
        at.session_state["active_product"] = FakeProduct()
        at.run()
        assert not at.exception, f"Page raised: {[e.value for e in at.exception]}"
        assert any("Failed to load CSV" in e.value for e in at.error)
        # The finally-based cleanup ran: the context holds no stale path
        assert at.session_state["temp_csv_context"].path is None


class TestTempCSVContext:
    """Unit tests for the single cleanup mechanism used by all page paths."""

    def test_set_path_and_cleanup_deletes_file(self, page_module, tmp_path):
        tmp = tmp_path / "upload.csv"
        tmp.write_text("Ticket ID\n1\n")
        ctx = page_module._TempCSVContext()
        ctx.set_path(tmp)
        assert tmp.exists()
        ctx.cleanup()
        assert not tmp.exists()
        assert ctx.path is None

    def test_cleanup_safe_when_no_file(self, page_module):
        ctx = page_module._TempCSVContext()
        ctx.cleanup()  # path is None -> no-op
        ctx.set_path(tmp_path_nonexistent := tmp_path_nonexistent_path())
        ctx.cleanup()  # path no longer exists -> no-op
        assert ctx.path is None

    def test_replacement_cleans_previous_file(self, page_module, tmp_path):
        """New upload replaces an old upload: the previous temp file is deleted."""
        old = tmp_path / "old.csv"
        new = tmp_path / "new.csv"
        old.write_text("a")
        new.write_text("b")
        ctx = page_module._TempCSVContext()
        ctx.set_path(old)
        ctx.set_path(new)
        assert not old.exists(), "previous upload temp file must be deleted"
        assert new.exists()
        ctx.cleanup()
        assert not new.exists()

    def test_exit_cleans_up_on_exception(self, page_module, tmp_path):
        """The context-manager protocol deletes the file when an exception unwinds."""
        tmp = tmp_path / "upload.csv"
        tmp.write_text("x")
        ctx = page_module._TempCSVContext()
        with pytest.raises(ValueError):
            with ctx:
                ctx.set_path(tmp)
                raise ValueError("simulated page error")
        assert not tmp.exists()
        assert ctx.path is None


def tmp_path_nonexistent_path():
    from pathlib import Path
    import tempfile

    return Path(tempfile.mkdtemp()) / "does_not_exist.csv"


class TestBundledDatasetSafety:
    """The bundled Kaggle source CSV must never be touched by cleanup."""

    def test_bundled_csv_exists_and_untouched(self, isolated_db, monkeypatch):
        before = BUNDLED_DATASET.stat().st_mtime_ns, BUNDLED_DATASET.stat().st_size
        _shrink_dataset(monkeypatch)
        at = _make_app()
        at.session_state["active_product"] = FakeProduct()
        at.run()
        assert not at.exception
        after = BUNDLED_DATASET.stat().st_mtime_ns, BUNDLED_DATASET.stat().st_size
        assert before == after, "bundled Kaggle CSV was modified or deleted"
        assert BUNDLED_DATASET.exists()
