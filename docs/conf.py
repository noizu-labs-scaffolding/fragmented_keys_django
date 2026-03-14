"""Sphinx configuration for fragmented-keys-django documentation."""

import os
import sys

# Add the project root so autodoc can find the package
sys.path.insert(0, os.path.abspath(".."))

# -- Django setup (required for autodoc to import Django modules) ----------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "docs._django_settings")

import django

django.setup()

# -- Project information ---------------------------------------------------
project = "fragmented-keys-django"
copyright = "2024, GreatNonProfit"
author = "GreatNonProfit"
release = "0.1.0"

# -- General configuration -------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "PROJ-*", "arch"]

# -- Options for HTML output -----------------------------------------------
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
}

# -- Extension configuration -----------------------------------------------

# Napoleon (Google/NumPy docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True

# Autodoc
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}

# Intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": ("https://docs.djangoproject.com/en/5.0/", "https://docs.djangoproject.com/en/5.0/_objects/"),
}

# MyST (Markdown support)
myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
