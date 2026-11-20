"""
Smoke tests for Streamlit application.
"""

import pytest
from pathlib import Path
import sys

# Add src to path - anchored to project root
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


def test_home_py_exists():
    """Test that Home.py exists."""
    home_path = project_root / "src" / "productsignal" / "app" / "Home.py"
    assert home_path.exists(), "Home.py should exist"


def test_home_py_imports():
    """Test that Home.py can be imported without errors."""
    import productsignal.app.Home as home_module
    assert hasattr(home_module, "main")


def test_streamlit_config():
    """Test that Streamlit page config is set."""
    import productsignal.app.Home as home_module
    import inspect

    source = inspect.getsource(home_module)
    assert "set_page_config" in source
    assert "ProductSignal" in source


def test_sidebar_rendering():
    """Test that sidebar rendering function exists."""
    import productsignal.app.Home as home_module
    import inspect

    source = inspect.getsource(home_module)
    assert "render_sidebar" in source


def test_home_page_rendering():
    """Test that home page rendering function exists."""
    import productsignal.app.Home as home_module
    import inspect

    source = inspect.getsource(home_module)
    assert "render_home_page" in source


def test_product_context_setup():
    """Test that product context setup function exists."""
    import productsignal.app.Home as home_module
    import inspect

    source = inspect.getsource(home_module)
    assert "render_product_context_setup" in source