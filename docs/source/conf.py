# Configuration file for the Sphinx documentation builder.

# -- Project information -----------------------------------------------------

project = "AWS setup at Harvard"
author = "Dandan Zhang"
copyright = "2026, Dandan Zhang"
release = "0.1.0"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.duration",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "titles_only": False,
}

# -- Options for EPUB output -------------------------------------------------

epub_show_urls = "footnote"
