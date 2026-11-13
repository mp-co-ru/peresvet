# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys
import datetime
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath('../../'))

sys.path.insert(0, os.path.abspath('../../src/services/alerts/api_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/alerts/app/'))
sys.path.insert(0, os.path.abspath('../../src/services/alerts/app_api/'))
sys.path.insert(0, os.path.abspath('../../src/services/alerts/model_crud/'))

sys.path.insert(0, os.path.abspath('../../src/services/connectors/api_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/connectors/model_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/connectors/app/'))

sys.path.insert(0, os.path.abspath('../../src/services/dataStorages/api_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/dataStorages/model_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/dataStorages/app/postgresql/'))
sys.path.insert(0, os.path.abspath('../../src/services/dataStorages/app/victoriametrics/'))

sys.path.insert(0, os.path.abspath('../../src/services/methods/api_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/methods/app/'))
sys.path.insert(0, os.path.abspath('../../src/services/methods/model_crud/'))

sys.path.insert(0, os.path.abspath('../../src/services/objects/api_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/objects/model_crud/'))

sys.path.insert(0, os.path.abspath('../../src/services/retranslator/app/'))

sys.path.insert(0, os.path.abspath('../../src/services/schedules/api_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/schedules/app/'))
sys.path.insert(0, os.path.abspath('../../src/services/schedules/model_crud/'))

sys.path.insert(0, os.path.abspath('../../src/services/tags/api_crud/'))
sys.path.insert(0, os.path.abspath('../../src/services/tags/app/'))
sys.path.insert(0, os.path.abspath('../../src/services/tags/app_api/'))
sys.path.insert(0, os.path.abspath('../../src/services/tags/model_crud/'))

project = 'МПК-Пересвет'
copyright = f'{datetime.date.today().year}, ООО Матч Поинт Консалтинг'
author = 'V.Badashkin'


def _release_version() -> str:
    """Номер релиза: PRS_VERSION, файл VERSION поставки или старшая метка v* в git.

    Метки релизов ставятся на коммиты main и в dev не попадают, поэтому
    git describe в dev показал бы устаревший релиз.
    """
    from_env = os.environ.get('PRS_VERSION', '').strip()
    if from_env:
        return from_env
    root = Path(__file__).resolve().parents[2]
    version_file = root / 'VERSION'
    if version_file.is_file():
        from_file = version_file.read_text(encoding='utf-8').strip()
        if from_file:
            return from_file
    try:
        tags = subprocess.run(
            ['git', '-C', str(root), 'tag', '--list', 'v*', '--sort=-v:refname'],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        tags = []
    return tags[0] if tags else ''


version = release = _release_version()

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinxcontrib.httpdomain',
    'sphinxcontrib.httpexample',
    'sphinx.ext.todo',
]

'''
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.mathjax',
    'sphinx.ext.ifconfig',
    'sphinx.ext.viewcode',
    'sphinx.ext.githubpages',
    'sphinx.ext.intersphinx',
    # uncomment to build pdf
    #'rst2pdf.pdfbuilder',
]
'''

httpexample_scheme = 'http'

# Sphinx 9 по умолчанию переписывает __annotations__ классов из исходников
# их модулей, включая pydantic.BaseModel. После этого pydantic не может
# построить модель с extra="allow" (DataGet в tags_app_api_svc).
autodoc_use_type_comments = False

templates_path = ['_templates']
exclude_patterns = []

language = 'ru'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_css_files = ['custom.css']
html_favicon = "_static/peresvet_middle.png"

source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

htmlhelp_basename = 'mpc_peresvet'


# -- Options for LaTeX output ------------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    'papersize': 'a4paper',

    # The font size ('10pt', '11pt' or '12pt').
    #
    'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',

    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, 'mpc_peresvet.tex', 'МПК-Пересвет',
     'ООО Матч Поинт Консалтинг', 'manual'),
]


# -- Options for manual page output ------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (master_doc, 'mpc_peresvet_doc', 'MПК-Пересвет. Документация',
     [author], 1)
]


# -- Options for Texinfo output ----------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, 'MPCPeresvetDoc', 'Платформа МПК-Пересвет. Документация.',
     author, 'MPCPeresvetDoc', 'Платформа МПК-Пересвет. Документация.',
     'Miscellaneous'),
]


# -- Extension configuration -------------------------------------------------

# -- Options for todo extension ----------------------------------------------

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True

html_logo = "pics/logo.png"
html_theme_options = {
    'logo_only': True,
}

pdf_documents = [('index', u'documentation', u'My Docs', u'Me'), ]
