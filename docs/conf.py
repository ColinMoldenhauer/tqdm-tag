project = "tqdm-tag"
copyright = "2026, Colin Moldenhauer"
author = "Colin Moldenhauer"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "myst_parser",
]

html_theme = "furo"
html_title = "tqdm-tag"

html_theme_options = {
    "source_repository": "https://github.com/ColinMoldenhauer/tqdm-tag",
    "source_branch": "main",
    "source_directory": "docs/",
}

autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = True

myst_enable_extensions = ["colon_fence"]
