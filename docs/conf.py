import re
import io
import os
# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# http://www.sphinx-doc.org/en/master/config

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
sys.path.insert(0, os.path.abspath(".."))

# -- Project information -----------------------------------------------------

project = 'Miney'
copyright = '2020, Robert Lieback'
author = 'Robert Lieback'


__version__ = re.search(
        r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]',  # It excludes inline comment too
        io.open(os.path.abspath(os.path.join("..", "miney", "__init__.py")), encoding='utf_8_sig').read()
    ).group(1)

# The full version, including alpha/beta/rc tags
release = __version__


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc", "sphinx.ext.viewcode", "sphinx.ext.intersphinx"
]
autodoc_default_options = {
    'members':         True,
    'member-order':    'alphabetical',
    # 'special-members': '__init__',
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_rtd_theme'

html_theme_options = {
    'logo_only': False,
    # 'collapse_navigation': False,
    # 'titles_only': True
}

html_logo = "miney-logo.png"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

todo_include_todos = True