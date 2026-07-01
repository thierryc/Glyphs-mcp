# -*- coding: utf-8 -*-

"""
reStructuredText parser for rich

Initial few lines gotten from: https://github.com/willmcgugan/rich/discussions/1263#discussioncomment-808898
There are a lot of improvements are added by me
"""
from io import StringIO
import textwrap
from html.parser import HTMLParser
import functools
import os
import re
import threading
from typing import Any, Callable, ClassVar, Dict, List, Literal, Optional, Tuple, Type, Union

# Imports from rich_rst._vendor.docutils package for the parsing
from rich_rst._vendor import docutils
import rich_rst._vendor.docutils.core
import rich_rst._vendor.docutils.frontend
import rich_rst._vendor.docutils.io
import rich_rst._vendor.docutils.nodes
import rich_rst._vendor.docutils.parsers.rst
import rich_rst._vendor.docutils.parsers.rst.directives
import rich_rst._vendor.docutils.parsers.rst.directives.tables
import rich_rst._vendor.docutils.utils

# Imports from the rich package for the printing
import rich
from rich import box
from rich.align import Align
from rich.console import Console, ConsoleOptions, RenderResult, NewLine, Group
from rich.jupyter import JupyterMixin
from rich.panel import Panel
from rich.style import Style
from rich.syntax import Syntax, SyntaxTheme
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from rich.segment import Segment
from rich.cells import cell_len
from rich.styled import Styled
from rich.terminal_theme import TerminalTheme, DEFAULT_TERMINAL_THEME

from pygments.lexers import guess_lexer, get_lexer_by_name
from pygments.util import ClassNotFound

import importlib.metadata

__all__ = ("RST", "ReStructuredText", "reStructuredText", "RestructuredText", "RSTVisitor")
__author__ = "Arian Mollik Wasi (aka. Wasi Master)"
__version__ = importlib.metadata.version(__package__ or __name__)


def _validate_default_lexer_name(default_lexer: Optional[str]) -> Optional[str]:
    """Validate that ``default_lexer`` is a known Pygments lexer alias."""
    if default_lexer is None:
        return default_lexer
    try:
        get_lexer_by_name(default_lexer)
    except ClassNotFound as error:
        raise ValueError(f"Unknown Pygments lexer name: {default_lexer!r}") from error
    return default_lexer


# ── Custom nodes for Sphinx directives ───────────────────────────────────────

class versionmodified(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node produced by the versionadded, versionchanged, and deprecated directives."""
    pass


class seealso(docutils.nodes.Admonition, docutils.nodes.Element):
    """Node produced by the seealso directive."""
    pass


class centered_block(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node for .. centered:: directive."""
    pass


class py_desc(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node for Python/C/C++/JS domain object-description directives."""
    pass


class toctree_stub(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node for .. toctree:: directive."""
    pass


class literalinclude_stub(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node for .. literalinclude:: directive."""
    pass


class glossary_block(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node for .. glossary:: directive."""
    pass


class hlist_block(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node for .. hlist:: directive carrying column-count metadata."""
    pass


class availability(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node produced by the availability directive."""
    pass


class soft_deprecated(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node produced by the soft-deprecated directive."""
    pass


class impl_detail(docutils.nodes.General, docutils.nodes.Body, docutils.nodes.Element):
    """Node produced by the impl-detail directive."""
    pass


# ── Docutils directive classes for Sphinx-specific directives ─────────────────

class _VersionDirective(docutils.parsers.rst.Directive):
    """Handles ``.. versionadded::``, ``.. versionchanged::``, and ``.. deprecated::``.

    Matches Sphinx's signature: the version is the first argument and an
    optional explanation is the second. ``final_argument_whitespace`` lets
    the explanation span the indented line(s) immediately following the
    directive (no blank line required), per the Python devguide form
    ``.. versionchanged:: 2.0\\n   Added the *spam* parameter.``.
    """

    required_arguments = 1
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {}
    has_content = True

    def run(self) -> List[docutils.nodes.Node]:
        node = versionmodified(type=self.name, version=self.arguments[0])
        if len(self.arguments) > 1:
            explanation = self.arguments[1]
            inline_nodes, messages = self.state.inline_text(explanation, self.lineno)
            node += docutils.nodes.paragraph(explanation, '', *inline_nodes)
            node += messages
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _SeeAlsoDirective(docutils.parsers.rst.Directive):
    """Handles ``.. seealso::``."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {}
    has_content = True

    def run(self) -> List[docutils.nodes.Node]:
        node = seealso()
        if self.arguments:
            node += docutils.nodes.paragraph(self.arguments[0], self.arguments[0])
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _CodeBlockDirective(docutils.parsers.rst.Directive):
    """Handles ``.. code-block::``, ``.. sourcecode::``, ``.. code::``."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = False
    has_content = True
    option_spec = {
        'linenos': docutils.parsers.rst.directives.flag,
        'emphasize-lines': docutils.parsers.rst.directives.unchanged,
        'caption': docutils.parsers.rst.directives.unchanged,
        'name': docutils.parsers.rst.directives.unchanged,
        'dedent': docutils.parsers.rst.directives.unchanged,
        'force': docutils.parsers.rst.directives.flag,
        'class': docutils.parsers.rst.directives.unchanged,
        'number-lines': docutils.parsers.rst.directives.nonnegative_int,
        'lineno-start': docutils.parsers.rst.directives.nonnegative_int,
    }

    def run(self) -> List[docutils.nodes.Node]:
        language = self.arguments[0] if self.arguments else None
        code = '\n'.join(self.content)
        # Support `:dedent:` option: either an integer number of spaces
        # to remove from each line, or empty/value-less to auto-dedent.
        dedent_opt = self.options.get('dedent')
        if dedent_opt is not None:
            if dedent_opt == '' or dedent_opt is True:
                code = textwrap.dedent(code)
            else:
                try:
                    n = int(dedent_opt)
                except (TypeError, ValueError):
                    code = textwrap.dedent(code)
                else:
                    new_lines = []
                    for line in code.splitlines():
                        # Remove up to n leading spaces from each line.
                        new_lines.append(re.sub(rf'^ {{0,{n}}}', '', line))
                    code = '\n'.join(new_lines)
        node = docutils.nodes.literal_block(code, code)
        if language:
            node['classes'] = ['code', language]
        else:
            node['classes'] = ['code']
        # Preserve directive options that are relevant to rendering
        # (e.g. :caption: and :name:) so the visitor can include them
        # in panel titles or elsewhere.
        caption_opt = self.options.get('caption')
        if caption_opt:
            node['caption'] = caption_opt
        name_opt = self.options.get('name')
        if name_opt:
            node['name'] = name_opt
        # Line number options: boolean `:linenos:` and numeric start
        linenos = 'linenos' in self.options
        if linenos:
            node['linenos'] = True
        # Support both Sphinx-style `:lineno-start:` and docutils `:number-lines:`
        if 'lineno-start' in self.options:
            try:
                node['start_line'] = int(self.options.get('lineno-start'))
            except (TypeError, ValueError):
                pass
        elif 'number-lines' in self.options:
            try:
                node['start_line'] = int(self.options.get('number-lines'))
            except (TypeError, ValueError):
                pass
        # Parse emphasize-lines option into a set of integers for Syntax.highlight_lines
        emphasize = self.options.get('emphasize-lines')
        if emphasize:
            highlight_lines = set()
            for part in emphasize.split(','):
                part = part.strip()
                if not part:
                    continue
                if '-' in part:
                    try:
                        start_s, end_s = part.split('-', 1)
                        start = int(start_s)
                        end = int(end_s)
                        if start <= end:
                            highlight_lines.update(range(start, end + 1))
                    except ValueError:
                        # ignore malformed ranges
                        continue
                else:
                    try:
                        highlight_lines.add(int(part))
                    except ValueError:
                        # ignore malformed numbers
                        continue
            if highlight_lines:
                node['highlight_lines'] = highlight_lines
        return [node]


class _MathDirective(docutils.parsers.rst.Directive):
    """Handles ``.. math::`` with Sphinx-compatible option parsing."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True
    option_spec = {
        'class': docutils.parsers.rst.directives.class_option,
        'name': docutils.parsers.rst.directives.unchanged,
        # Sphinx-specific options. These are accepted and preserved as node
        # attributes but intentionally no-op in terminal rendering.
        'nowrap': docutils.parsers.rst.directives.flag,
        'label': docutils.parsers.rst.directives.unchanged,
    }

    def run(self) -> List[docutils.nodes.Node]:
        blocks: List[str] = []
        if self.arguments:
            argument = self.arguments[0].strip()
            if argument:
                blocks.append(argument)
        if self.content:
            blocks.extend(block for block in '\n'.join(self.content).split('\n\n') if block)

        nodes: List[docutils.nodes.Node] = []
        for block in blocks:
            node = docutils.nodes.math_block(self.block_text, block)
            node['classes'] += self.options.get('class', [])
            if 'nowrap' in self.options:
                node['nowrap'] = True
            if 'label' in self.options:
                node['label'] = self.options['label']
            source, line = self.state_machine.get_source_and_line(self.lineno)
            node.source = source
            node.line = line
            self.add_name(node)
            nodes.append(node)
        return nodes


class _HighlightDirective(docutils.parsers.rst.Directive):
    """Handles ``.. highlight::``."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = False
    option_spec = {
        'linenothreshold': docutils.parsers.rst.directives.nonnegative_int,
        'force': docutils.parsers.rst.directives.flag,
    }

    def run(self) -> List[docutils.nodes.Node]:
        return []


class _SilentDirective(docutils.parsers.rst.Directive):
    """No-op directive for index, tabularcolumns, etc."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        return []


class _CurrentModuleDirective(docutils.parsers.rst.Directive):
    """No-op directive for currentmodule, py:currentmodule."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = False
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        return []


class _OnlyDirective(docutils.parsers.rst.Directive):
    """Handles ``.. only::`` — always renders content."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = True
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        container = docutils.nodes.container()
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, container)
        return container.children


class _CenteredDirective(docutils.parsers.rst.Directive):
    """Handles ``.. centered::``."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = False
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        return [centered_block(text=self.arguments[0])]


class _HlistDirective(docutils.parsers.rst.Directive):
    """Handles ``.. hlist::`` — renders as a multi-column table."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = True
    option_spec = {
        'columns': docutils.parsers.rst.directives.nonnegative_int,
    }

    def run(self) -> List[docutils.nodes.Node]:
        columns = self.options.get('columns', 2) or 2
        node = hlist_block(columns=columns)
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


def _parse_toctree_numbered(argument: Optional[str]) -> int:
    if argument is None:
        return 0
    value = argument.strip()
    if not value:
        return 0
    return docutils.parsers.rst.directives.nonnegative_int(value)


class _ToctreeDirective(docutils.parsers.rst.Directive):
    """Handles ``.. toctree::``."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = True
    option_spec = {
        'maxdepth': docutils.parsers.rst.directives.nonnegative_int,
        'caption': docutils.parsers.rst.directives.unchanged,
        'name': docutils.parsers.rst.directives.unchanged,
        'titlesonly': docutils.parsers.rst.directives.flag,
        'glob': docutils.parsers.rst.directives.flag,
        'hidden': docutils.parsers.rst.directives.flag,
        'includehidden': docutils.parsers.rst.directives.flag,
        'reversed': docutils.parsers.rst.directives.flag,
        'numbered': _parse_toctree_numbered,
    }

    def run(self) -> List[docutils.nodes.Node]:
        caption = self.options.get('caption', 'Contents')
        maxdepth = self.options.get('maxdepth', 0)
        entries = [
            line.strip() for line in self.content
            if line.strip() and not line.strip().startswith(':')
        ]
        reversed_entries = 'reversed' in self.options
        numbered_enabled = 'numbered' in self.options
        numbered_depth = self.options.get('numbered', 0)
        node = toctree_stub()
        node['caption'] = caption
        node['entries'] = entries
        node['maxdepth'] = maxdepth
        node['reversed'] = reversed_entries
        node['numbered_enabled'] = numbered_enabled
        node['numbered'] = numbered_depth
        return [node]


class _LiteralIncludeDirective(docutils.parsers.rst.Directive):
    """Handles ``.. literalinclude::``."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = False
    option_spec = {
        'language': docutils.parsers.rst.directives.unchanged,
        'linenos': docutils.parsers.rst.directives.flag,
        'lines': docutils.parsers.rst.directives.unchanged,
        'start-after': docutils.parsers.rst.directives.unchanged,
        'end-before': docutils.parsers.rst.directives.unchanged,
        'encoding': docutils.parsers.rst.directives.unchanged,
        'dedent': docutils.parsers.rst.directives.unchanged,
        'tab-width': docutils.parsers.rst.directives.nonnegative_int,
        'caption': docutils.parsers.rst.directives.unchanged,
        'name': docutils.parsers.rst.directives.unchanged,
        'start-at': docutils.parsers.rst.directives.unchanged,
        'end-at': docutils.parsers.rst.directives.unchanged,
        'prepend': docutils.parsers.rst.directives.unchanged,
        'append': docutils.parsers.rst.directives.unchanged,
        'force': docutils.parsers.rst.directives.flag,
        'diff': docutils.parsers.rst.directives.unchanged,
    }

    def run(self) -> List[docutils.nodes.Node]:
        node = literalinclude_stub()
        node['filename'] = self.arguments[0]

        # Attempt to resolve and read the referenced file so the visitor can
        # render real content instead of a mere placeholder.
        rel_path = self.arguments[0]
        source_file = self.state_machine.get_source(self.lineno)
        if source_file and source_file not in ('<string>', '<stdin>', '<rst-document>'):
            base_dir = os.path.dirname(os.path.abspath(source_file))
            abs_path = os.path.join(base_dir, rel_path)
        else:
            abs_path = os.path.abspath(rel_path)

        language = self.options.get('language', '')
        encoding = self.options.get('encoding', 'utf-8')
        lines_opt = self.options.get('lines', '')
        linenos = 'linenos' in self.options

        try:
            with open(abs_path, encoding=encoding) as fh:
                content = fh.read()

            # Apply the ``lines`` option if provided (e.g., "1-5,8,10-20").
            if lines_opt:
                all_lines = content.splitlines(keepends=True)
                selected = []
                for part in lines_opt.split(','):
                    part = part.strip()
                    if '-' in part:
                        start_s, end_s = part.split('-', 1)
                        selected.extend(all_lines[int(start_s) - 1 : int(end_s)])
                    elif part:
                        selected.append(all_lines[int(part) - 1])
                content = ''.join(selected)

            node['content'] = content
            node['language'] = language
            node['linenos'] = linenos
        except (OSError, ValueError, IndexError):
            # File not found or unreadable — fall back to placeholder rendering.
            pass

        return [node]


class _ProductionListDirective(docutils.parsers.rst.Directive):
    """Handles ``.. productionlist::``."""

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        if self.content:
            code = '\n'.join(self.content)
        elif self.arguments:
            code = self.arguments[0]
        else:
            code = ''
        node = docutils.nodes.literal_block(code, code)
        node['classes'] = ['code', 'productionlist']
        return [node]


class _IncludeDirective(docutils.parsers.rst.Directive):
    """Handles ``.. include::`` — reads an external RST file and inlines it.

    Paths are resolved relative to the source document.  When ``safe_include``
    is ``True`` (the default), path traversal outside the source directory is
    rejected.  If the file cannot be read the directive emits a warning
    admonition instead of raising an error.
    """

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = False
    option_spec = {
        'encoding': docutils.parsers.rst.directives.unchanged,
        'start-line': docutils.parsers.rst.directives.nonnegative_int,
        'end-line': docutils.parsers.rst.directives.nonnegative_int,
    }

    def run(self) -> List[docutils.nodes.Node]:
        rel_path = self.arguments[0]
        source_file = self.state_machine.get_source(self.lineno)
        if source_file and source_file not in ('<string>', '<stdin>', '<rst-document>'):
            base_dir = os.path.dirname(os.path.abspath(source_file))
        else:
            base_dir = os.getcwd()

        abs_path = os.path.normpath(os.path.join(base_dir, rel_path))

        # Safety: reject path traversal outside the base directory.
        try:
            common = os.path.commonpath([abs_path, base_dir])
        except ValueError:
            # commonpath raises ValueError on Windows when paths are on
            # different drives — treat that as a traversal attempt.
            common = None
        if common != base_dir:
            stub = docutils.nodes.warning()
            stub += docutils.nodes.paragraph(
                text=f"Rejected include path outside source directory: {rel_path!r}"
            )
            return [stub]

        encoding = self.options.get('encoding', 'utf-8')
        start_line = self.options.get('start-line', None)
        end_line = self.options.get('end-line', None)

        try:
            with open(abs_path, encoding=encoding) as fh:
                content = fh.read()

            if start_line is not None or end_line is not None:
                lines = content.splitlines()
                content = '\n'.join(lines[start_line or 0:end_line])

            # Parse the included RST content as a nested document.
            import rich_rst._vendor.docutils.statemachine as _sm
            content_lines = _sm.StringList(
                content.splitlines(), source=abs_path
            )
            container = docutils.nodes.container()
            self.state.nested_parse(content_lines, 0, container)
            return container.children

        except (OSError, UnicodeDecodeError):
            stub = docutils.nodes.warning()
            stub += docutils.nodes.paragraph(
                text=f"Could not include file: {rel_path!r}"
            )
            return [stub]


class _GlossaryDirective(docutils.parsers.rst.Directive):
    """Handles ``.. glossary::``."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = True
    option_spec = {
        'sorted': docutils.parsers.rst.directives.flag,
    }

    def run(self) -> List[docutils.nodes.Node]:
        container = glossary_block()
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, container)
        if 'sorted' in self.options:
            for child in container.children:
                if isinstance(child, docutils.nodes.definition_list):
                    child.children.sort(
                        key=lambda item: item.children[0].astext().strip().casefold()
                        if item.children
                        else ""
                    )
        return [container]


class _DeprecatedRemovedDirective(docutils.parsers.rst.Directive):
    """Handles ``.. deprecated-removed::``."""

    required_arguments = 2
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = True
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        version_str = f"{self.arguments[0]} (removed in {self.arguments[1]})"
        node = versionmodified(type='deprecated-removed', version=version_str)
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _AvailabilityDirective(docutils.parsers.rst.Directive):
    """Handles ``.. availability::``.\n\n    The version is the first required argument. An optional explanation can\n    follow on the next indented line(s).
    """

    required_arguments = 1
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        node = availability(version=self.arguments[0])
        if len(self.arguments) > 1:
            explanation = self.arguments[1]
            inline_nodes, messages = self.state.inline_text(explanation, self.lineno)
            node += docutils.nodes.paragraph(explanation, '', *inline_nodes)
            node += messages
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _SoftDeprecatedDirective(docutils.parsers.rst.Directive):
    """Handles ``.. soft-deprecated::``.\n\n    The version is the first required argument. An optional explanation can\n    follow on the next indented line(s).
    """

    required_arguments = 1
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        node = soft_deprecated(version=self.arguments[0])
        if len(self.arguments) > 1:
            explanation = self.arguments[1]
            inline_nodes, messages = self.state.inline_text(explanation, self.lineno)
            node += docutils.nodes.paragraph(explanation, '', *inline_nodes)
            node += messages
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _ImplDetailDirective(docutils.parsers.rst.Directive):
    """Handles ``.. impl-detail::``."""

    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    has_content = True
    option_spec = {}

    def run(self) -> List[docutils.nodes.Node]:
        node = impl_detail()
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _PyObjectDirective(docutils.parsers.rst.Directive):
    """Handles Python/C/C++/JS domain object-description directives."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = True
    option_spec = {
        'no-index': docutils.parsers.rst.directives.flag,
        'noindex': docutils.parsers.rst.directives.flag,
        'module': docutils.parsers.rst.directives.unchanged,
        'annotation': docutils.parsers.rst.directives.unchanged,
        'type': docutils.parsers.rst.directives.unchanged,
        'value': docutils.parsers.rst.directives.unchanged,
        'async': docutils.parsers.rst.directives.flag,
        'classmethod': docutils.parsers.rst.directives.flag,
        'staticmethod': docutils.parsers.rst.directives.flag,
        'abstract': docutils.parsers.rst.directives.flag,
        'final': docutils.parsers.rst.directives.flag,
        'canonical': docutils.parsers.rst.directives.unchanged,
        'platform': docutils.parsers.rst.directives.unchanged,
        'synopsis': docutils.parsers.rst.directives.unchanged,
        'deprecated': docutils.parsers.rst.directives.flag,
    }

    def run(self) -> List[docutils.nodes.Node]:
        if ':' in self.name:
            domain, _, objtype = self.name.partition(':')
        else:
            domain = "py"
            objtype = self.name
        node = py_desc(domain=domain, objtype=objtype, sig=self.arguments[0])
        if self.options:
            node['options'] = dict(self.options)
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _AutodocDirective(docutils.parsers.rst.Directive):
    """Handles autodoc directives (automodule, autoclass, etc.)."""

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = True
    option_spec = {
        'members': docutils.parsers.rst.directives.unchanged,
        'undoc-members': docutils.parsers.rst.directives.flag,
        'show-inheritance': docutils.parsers.rst.directives.flag,
        'member-order': docutils.parsers.rst.directives.unchanged,
        'exclude-members': docutils.parsers.rst.directives.unchanged,
        'private-members': docutils.parsers.rst.directives.unchanged,
        'special-members': docutils.parsers.rst.directives.unchanged,
        'inherited-members': docutils.parsers.rst.directives.unchanged,
        'no-index': docutils.parsers.rst.directives.flag,
        'noindex': docutils.parsers.rst.directives.flag,
        'synopsis': docutils.parsers.rst.directives.unchanged,
        'platform': docutils.parsers.rst.directives.unchanged,
        'deprecated': docutils.parsers.rst.directives.flag,
        'ignore-module-all': docutils.parsers.rst.directives.flag,
    }

    def run(self) -> List[docutils.nodes.Node]:
        return []


# ── flat-table directive ───────────────────────────────────────────────────────
# The flat-table directive is described in the Linux kernel Sphinx documentation
# guide (https://www.kernel.org/doc/html/latest/doc-guide/sphinx.html).
# This is an independent implementation.

class _rowSpan(docutils.nodes.General, docutils.nodes.Element):
    """Inline node carrying a row-span value for flat-table cells."""
    pass


class _colSpan(docutils.nodes.General, docutils.nodes.Element):
    """Inline node carrying a column-span value for flat-table cells."""
    pass


def _flat_table_cspan(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: Any,
    options: Optional[Dict[str, Any]] = None,
    content: Optional[List[str]] = None,
) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
    """Role handler for ``:cspan:`` — extra columns a cell spans."""
    try:
        n = int(text)
        if n < 0:
            raise ValueError
    except ValueError:
        msg = inliner.reporter.error(
            f":cspan: requires a non-negative integer, got {text!r}",
            line=lineno,
        )
        return [inliner.problematic(rawtext, rawtext, msg)], [msg]
    return [_colSpan(span=n)], []


def _flat_table_rspan(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: Any,
    options: Optional[Dict[str, Any]] = None,
    content: Optional[List[str]] = None,
) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
    """Role handler for ``:rspan:`` — extra rows a cell spans."""
    try:
        n = int(text)
        if n < 0:
            raise ValueError
    except ValueError:
        msg = inliner.reporter.error(
            f":rspan: requires a non-negative integer, got {text!r}",
            line=lineno,
        )
        return [inliner.problematic(rawtext, rawtext, msg)], [msg]
    return [_rowSpan(span=n)], []


class _FlatTableDirective(docutils.parsers.rst.directives.tables.Table):
    """Implementation of the ``flat-table`` directive.

    A flat-table is written as a two-level bullet list.  The outer items are
    rows; the inner items are cells.  Cells may carry ``:rspan:`` and
    ``:cspan:`` roles to span rows or columns.  Missing cells on the right
    side of a row are auto-extended (or filled with empty cells when
    ``:fill-cells:`` is given).
    """

    option_spec = {
        'name': docutils.parsers.rst.directives.unchanged,
        'class': docutils.parsers.rst.directives.class_option,
        'header-rows': docutils.parsers.rst.directives.nonnegative_int,
        'stub-columns': docutils.parsers.rst.directives.nonnegative_int,
        'widths': docutils.parsers.rst.directives.positive_int_list,
        'fill-cells': docutils.parsers.rst.directives.flag,
    }

    def run(self) -> List[docutils.nodes.Node]:
        if not self.content:
            error = self.state_machine.reporter.error(
                'The "%s" directive is empty; content required.' % self.name,
                docutils.nodes.literal_block(self.block_text, self.block_text),
                line=self.lineno,
            )
            return [error]

        title, messages = self.make_title()
        node = docutils.nodes.Element()
        self.state.nested_parse(self.content, self.content_offset, node)

        builder = _FlatTableBuilder(self)
        builder.parse_flat_table_node(node)
        table_node = builder.build_table_node()
        if title:
            table_node.insert(0, title)
        return [table_node] + messages


class _FlatTableBuilder:
    """Converts a two-level bullet list into a docutils ``table`` node."""

    def __init__(self, directive: _FlatTableDirective) -> None:
        self.directive = directive
        self.rows: List[List[Any]] = []
        self.max_cols = 0

    def build_table_node(self) -> docutils.nodes.table:
        col_widths = self.directive.get_column_widths(self.max_cols)
        if isinstance(col_widths, tuple):
            col_widths = col_widths[1]

        stub_columns = self.directive.options.get('stub-columns', 0)
        header_rows = self.directive.options.get('header-rows', 0)

        table = docutils.nodes.table()
        tgroup = docutils.nodes.tgroup(cols=len(col_widths))
        table += tgroup

        remaining_stubs = stub_columns
        for colwidth in col_widths:
            colspec = docutils.nodes.colspec(colwidth=colwidth)
            if remaining_stubs:
                colspec.attributes['stub'] = 1
                remaining_stubs -= 1
            tgroup += colspec

        if header_rows:
            thead = docutils.nodes.thead()
            tgroup += thead
            for row in self.rows[:header_rows]:
                thead += self._build_row_node(row)

        tbody = docutils.nodes.tbody()
        tgroup += tbody
        for row in self.rows[header_rows:]:
            tbody += self._build_row_node(row)

        return table

    def _build_row_node(self, row_data: List[Any]) -> docutils.nodes.row:
        row = docutils.nodes.row()
        for cell in row_data:
            if cell is None:
                continue
            cspan, rspan, cell_elements = cell
            attrs: Dict[str, Any] = {'classes': []}
            if rspan:
                attrs['morerows'] = rspan
            if cspan:
                attrs['morecols'] = cspan
            entry = docutils.nodes.entry(**attrs)
            entry.extend(cell_elements)
            row += entry
        return row

    def _raise_error(self, msg: str) -> None:
        error = self.directive.state_machine.reporter.error(
            msg,
            docutils.nodes.literal_block(
                self.directive.block_text, self.directive.block_text
            ),
            line=self.directive.lineno,
        )
        from rich_rst._vendor.docutils.utils import SystemMessagePropagation
        raise SystemMessagePropagation(error)

    def parse_flat_table_node(self, node: docutils.nodes.Element) -> None:
        if len(node) != 1 or not isinstance(node[0], docutils.nodes.bullet_list):
            self._raise_error(
                'Error parsing content block for the "%s" directive: '
                'exactly one bullet list expected.' % self.directive.name
            )

        for row_num, row_item in enumerate(node[0]):
            row = self._parse_row_item(row_item, row_num)
            self.rows.append(row)

        self._build_grid()

    def _build_grid(self) -> None:
        """Assign column positions to cells and insert None placeholders for spanned slots.

        Phase 1: walk rows in order, tracking which (row, col) positions are
        already claimed by a spanning cell via an occupancy set.  Each cell
        lands in the first unoccupied column in its row.

        Phase 2: rebuild self.rows as flat lists (None for occupied slots,
        tuple for real cells) and pad the right edge with auto-span or
        fill-cells as requested.
        """
        occupied: set = set()  # (row_idx, col_idx) positions pre-filled by a span
        positioned: List[List[Any]] = []

        for r, row in enumerate(self.rows):
            col = 0
            row_cells: List[Any] = []
            for cspan, rspan, content in row:
                while (r, col) in occupied:
                    col += 1
                row_cells.append((col, cspan, rspan, content))
                for dr in range(rspan + 1):
                    for dc in range(cspan + 1):
                        if dr > 0 or dc > 0:
                            occupied.add((r + dr, col + dc))
                col += cspan + 1
            positioned.append(row_cells)

        for row_cells in positioned:
            for col, cspan, _rspan, _content in row_cells:
                self.max_cols = max(self.max_cols, col + cspan + 1)

        fill_cells = 'fill-cells' in self.directive.options
        self.rows = []
        for row_cells in positioned:
            row: List[Any] = []
            col_cursor = 0
            for col, cspan, rspan, content in row_cells:
                while col_cursor < col:
                    row.append(None)
                    col_cursor += 1
                row.append((cspan, rspan, content))
                col_cursor += cspan + 1
            missing = self.max_cols - col_cursor
            if missing > 0:
                if not fill_cells:
                    if row and row[-1] is not None:
                        cspan, rspan, content = row[-1]
                        row[-1] = (cspan + missing, rspan, content)
                    else:
                        row.append((missing - 1, 0, []))
                else:
                    for _ in range(missing):
                        row.append((0, 0, [docutils.nodes.comment()]))
            self.rows.append(row)

    def _parse_row_item(self, row_item: docutils.nodes.list_item, row_num: int) -> List[Any]:
        row: List[Any] = []
        child_no = 0
        error = False
        cell_list = None

        for child in row_item:
            if isinstance(child, (docutils.nodes.comment, docutils.nodes.system_message)):
                pass
            elif isinstance(child, docutils.nodes.target):
                pass
            elif isinstance(child, docutils.nodes.bullet_list):
                child_no += 1
                cell_list = child
            else:
                error = True
                break

        if child_no != 1 or error:
            self._raise_error(
                'Error parsing content block for the "%s" directive: '
                'two-level bullet list expected, but row %s does not '
                'contain a second-level bullet list.'
                % (self.directive.name, row_num + 1)
            )

        for cell_item in cell_list:
            cspan, rspan, cell_elements = self._parse_cell_item(cell_item)
            row.append((cspan, rspan, cell_elements))
        return row

    def _parse_cell_item(
        self, cell_item: docutils.nodes.list_item
    ) -> Tuple[int, int, List[docutils.nodes.Node]]:
        cspan = rspan = 0
        if not len(cell_item):
            return cspan, rspan, []
        for elem in list(cell_item.findall(_colSpan)):
            cspan = elem.get('span')
            elem.parent.remove(elem)
        for elem in list(cell_item.findall(_rowSpan)):
            rspan = elem.get('span')
            elem.parent.remove(elem)
        return cspan, rspan, list(cell_item)


_sphinx_directives_registered = False
# This lock serialises one-time directive and role registration within a
# single Python process.  Each worker process in a multi-process build gets
# its own GIL, its own module state, and therefore its own lock — registration
# happens independently (and correctly) in every process.
_sphinx_registration_lock = threading.Lock()


def _sphinx_registration_guard(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with _sphinx_registration_lock:
            return function(*args, **kwargs)

    return wrapper


def _register_sphinx_directives() -> None:
    """Register Sphinx-specific directives so they render properly instead of as errors."""
    global _sphinx_directives_registered

    with _sphinx_registration_lock:
        if _sphinx_directives_registered:
            return

        docutils.parsers.rst.directives.register_directive('versionadded', _VersionDirective)
        docutils.parsers.rst.directives.register_directive('versionchanged', _VersionDirective)
        docutils.parsers.rst.directives.register_directive('deprecated', _VersionDirective)
        docutils.parsers.rst.directives.register_directive('seealso', _SeeAlsoDirective)

        # code-block
        for name in ('code-block', 'sourcecode', 'code'):
            docutils.parsers.rst.directives.register_directive(name, _CodeBlockDirective)
        # math (accept Sphinx options like :nowrap: and :label:)
        docutils.parsers.rst.directives.register_directive('math', _MathDirective)
        # highlight
        docutils.parsers.rst.directives.register_directive('highlight', _HighlightDirective)
        # silent no-op
        for name in ('index', 'tabularcolumns'):
            docutils.parsers.rst.directives.register_directive(name, _SilentDirective)
        # current module
        for name in ('currentmodule', 'py:currentmodule'):
            docutils.parsers.rst.directives.register_directive(name, _CurrentModuleDirective)
        # only
        docutils.parsers.rst.directives.register_directive('only', _OnlyDirective)
        # centered
        docutils.parsers.rst.directives.register_directive('centered', _CenteredDirective)
        # hlist
        docutils.parsers.rst.directives.register_directive('hlist', _HlistDirective)
        # toctree
        docutils.parsers.rst.directives.register_directive('toctree', _ToctreeDirective)
        # literalinclude
        docutils.parsers.rst.directives.register_directive('literalinclude', _LiteralIncludeDirective)
        # productionlist
        docutils.parsers.rst.directives.register_directive('productionlist', _ProductionListDirective)
        # glossary
        docutils.parsers.rst.directives.register_directive('glossary', _GlossaryDirective)
        # deprecated-removed
        docutils.parsers.rst.directives.register_directive('deprecated-removed', _DeprecatedRemovedDirective)
        # availability
        docutils.parsers.rst.directives.register_directive('availability', _AvailabilityDirective)
        # soft-deprecated
        docutils.parsers.rst.directives.register_directive('soft-deprecated', _SoftDeprecatedDirective)
        # impl-detail
        docutils.parsers.rst.directives.register_directive('impl-detail', _ImplDetailDirective)
        # include (safe custom implementation with path-traversal guard)
        docutils.parsers.rst.directives.register_directive('include', _IncludeDirective)
        # class and role: no visual output in terminal rendering; register as no-ops
        # to prevent "Unknown directive" errors in Sphinx-style documents.
        for name in ('class', 'role'):
            docutils.parsers.rst.directives.register_directive(name, _SilentDirective)
        # Python domain object descriptions
        for name in (
            'py:function', 'py:class', 'py:method', 'py:attribute', 'py:data',
            'py:exception', 'py:module', 'py:property', 'py:decorator',
            'py:classmethod', 'py:staticmethod', 'py:variable', 'py:type',
            'py:typevar', 'py:typealias', 'py:envvar', 'py:option',
            'py:coroutinefunction',
            'py:coroutinemethod', 'py:decoratorfunction', 'py:abstractmethod',
            'py:opcode', 'py:describe',
            # C domain
            'c:function', 'c:type', 'c:struct', 'c:union', 'c:enum',
            'c:enumerator', 'c:member', 'c:var', 'c:macro',
            # C++ domain
            'cpp:function', 'cpp:class', 'cpp:type', 'cpp:member', 'cpp:var',
            'cpp:enum', 'cpp:enumerator', 'cpp:concept', 'cpp:alias',
            # JavaScript domain
            'js:function', 'js:class', 'js:method', 'js:attribute', 'js:data',
            'js:module',
        ):
            docutils.parsers.rst.directives.register_directive(name, _PyObjectDirective)
        # autodoc
        for name in (
            'automodule', 'autoclass', 'autofunction', 'automethod',
            'autoattribute', 'autoexception', 'autodata', 'autoproperty',
            'autodecorator', 'autoclassmethod', 'autostaticmethod',
        ):
            docutils.parsers.rst.directives.register_directive(name, _AutodocDirective)
        # flat-table (Linux kernel docs extension)
        docutils.parsers.rst.directives.register_directive('flat-table', _FlatTableDirective)
        # cspan / rspan roles used inside flat-table cells
        import rich_rst._vendor.docutils.parsers.rst.roles as _roles
        import rich_rst._vendor.docutils.parsers.rst.languages.en as _en
        _roles.register_canonical_role('cspan', _flat_table_cspan)
        _roles.register_canonical_role('rspan', _flat_table_rspan)
        if hasattr(_en, 'roles'):
            _en.roles['cspan'] = 'cspan'
            _en.roles['rspan'] = 'rspan'

        _sphinx_directives_registered = True


_sphinx_roles_registered = False


def _register_sphinx_roles() -> None:
    """Register common Sphinx roles to gracefully handle Sphinx-specific markup.

    Sphinx roles like :func:, :class:, :meth: are very common in Python
    docstrings but are not available in standard docutils.  This function
    registers them to render as inline code/literal text instead of errors.

    Thread safety: protected by ``_sphinx_registration_lock``, identical to
    :func:`_register_sphinx_directives`.  Per-process state only — each
    worker in a multi-process build registers independently, which is correct.
    """
    global _sphinx_roles_registered

    with _sphinx_registration_lock:
        if _sphinx_roles_registered:
            return

        from rich_rst._vendor import docutils
        import rich_rst._vendor.docutils.parsers.rst.roles
        import rich_rst._vendor.docutils.parsers.rst.languages.en

        def sphinx_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            """Generic Sphinx role handler that renders as inline literal text."""
            display_text = text
            if '<' in text and text.endswith('>'):
                bracket_pos = text.rfind('<')
                potential_display = text[:bracket_pos].strip()
                if potential_display:
                    display_text = potential_display

            node = docutils.nodes.literal(rawtext, display_text)
            return [node], []

        sphinx_roles = [
            'func', 'function',
            'meth', 'method',
            'class',
            'mod', 'module',
            'attr', 'attribute',
            'obj', 'object',
            'data',
            'const', 'constant',
            'exc', 'exception',
            'var', 'variable',
            'type',
            'py:func', 'py:meth', 'py:class', 'py:mod', 'py:attr',
            'py:obj', 'py:data', 'py:const', 'py:exc',
            # Standard domain cross-reference roles
            'envvar', 'token', 'option', 'term', 'ref', 'doc', 'any', 'numref', 'download',
            # Misc
            'mailheader', 'mimetype', 'newsgroup', 'makevar', 'regexp',
            # Keyboard/GUI
            'kbd', 'guilabel',
            # Unix man pages
            'manpage',
            # Python domain additional
            'py:variable', 'py:type', 'py:property', 'py:parameter', 'py:typevar',
            # C domain
            'c:func', 'c:function', 'c:type', 'c:struct', 'c:union', 'c:enum', 'c:enumerator',
            'c:member', 'c:var', 'c:macro', 'c:expr', 'c:texpr',
            # C++ domain
            'cpp:func', 'cpp:function', 'cpp:class', 'cpp:type', 'cpp:member', 'cpp:var',
            'cpp:enum', 'cpp:enumerator', 'cpp:concept', 'cpp:expr', 'cpp:texpr', 'cpp:alias',
            # JavaScript domain
            'js:mod', 'js:module', 'js:func', 'js:function', 'js:data',
            'js:attr', 'js:attribute', 'js:class', 'js:meth', 'js:method',
        ]

        for role in sphinx_roles:
            docutils.parsers.rst.roles.register_canonical_role(role, sphinx_role)
            # Also register in language module to avoid INFO messages
            if hasattr(docutils.parsers.rst.languages.en, 'roles'):
                docutils.parsers.rst.languages.en.roles[role] = role

        # `:command:` and `:program:` → bold literal
        def _bold_literal_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            display_text = text
            if '<' in text and text.endswith('>'):
                bracket_pos = text.rfind('<')
                potential_display = text[:bracket_pos].strip()
                if potential_display:
                    display_text = potential_display
            node = docutils.nodes.strong(rawtext, display_text)
            return [node], []

        for _role_name in ('command', 'program'):
            docutils.parsers.rst.roles.register_canonical_role(_role_name, _bold_literal_role)
            if hasattr(docutils.parsers.rst.languages.en, 'roles'):
                docutils.parsers.rst.languages.en.roles[_role_name] = _role_name

        # `:dfn:` → emphasis (italic)
        def _dfn_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            node = docutils.nodes.emphasis(rawtext, text)
            return [node], []

        docutils.parsers.rst.roles.register_canonical_role('dfn', _dfn_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['dfn'] = 'dfn'

        # `:abbr:` → abbreviation node with explanation
        _abbr_re = re.compile(r'\((.*)\)$', re.DOTALL)

        def _abbr_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            matched = _abbr_re.search(text)
            if matched:
                abbr_text = text[:matched.start()].strip()
                explanation = matched.group(1)
            else:
                abbr_text = text
                explanation = ''
            node = docutils.nodes.abbreviation(rawtext, abbr_text, explanation=explanation)
            return [node], []

        docutils.parsers.rst.roles.register_canonical_role('abbr', _abbr_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['abbr'] = 'abbr'

        # `:menuselection:` → replace `-->` with ` ▶ `
        def _menuselection_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            text = text.replace('-->', '\u25b6')
            node = docutils.nodes.literal(rawtext, text)
            return [node], []

        docutils.parsers.rst.roles.register_canonical_role('menuselection', _menuselection_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['menuselection'] = 'menuselection'

        # `:samp:` and `:file:` → literal with {} stripped
        _braces_re = re.compile(r'\{([^}]*)\}')

        def _samp_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            clean = _braces_re.sub(r'\1', text)
            node = docutils.nodes.literal(rawtext, clean)
            return [node], []

        for _role_name in ('samp', 'file'):
            docutils.parsers.rst.roles.register_canonical_role(_role_name, _samp_role)
            if hasattr(docutils.parsers.rst.languages.en, 'roles'):
                docutils.parsers.rst.languages.en.roles[_role_name] = _role_name

        # `:pep:` → clickable PEP link
        def _pep_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            parts = text.split('#', 1)
            pep_num_str = parts[0].strip()
            anchor = ('#' + parts[1]) if len(parts) > 1 else ''
            try:
                pep_num = int(pep_num_str)
                url = f"https://peps.python.org/pep-{pep_num:04d}/{anchor}"
            except ValueError:
                url = "https://peps.python.org/"
            display = f"PEP {pep_num_str}"
            ref = docutils.nodes.reference(rawtext, display, refuri=url)
            return [ref], []

        docutils.parsers.rst.roles.register_canonical_role('pep', _pep_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['pep'] = 'pep'

        # `:rfc:` → clickable RFC link
        def _rfc_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Optional[Dict[str, Any]] = None, content: Optional[List[str]] = None) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            parts = text.split('#', 1)
            rfc_num_str = parts[0].strip()
            anchor = ('#' + parts[1]) if len(parts) > 1 else ''
            try:
                rfc_num = int(rfc_num_str)
                url = f"https://datatracker.ietf.org/doc/html/rfc{rfc_num}{anchor}"
            except ValueError:
                url = "https://datatracker.ietf.org/"
            display = f"RFC {rfc_num_str}"
            ref = docutils.nodes.reference(rawtext, display, refuri=url)
            return [ref], []

        docutils.parsers.rst.roles.register_canonical_role('rfc', _rfc_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['rfc'] = 'rfc'

        # `:cve:` → clickable CVE link
        def _cve_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any,
                    options: Optional[Dict[str, Any]] = None,
                    content: Optional[List[str]] = None
                    ) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            cve_id = text.strip().lstrip("CVE-")
            url = f"https://www.cve.org/CVERecord?id=CVE-{cve_id}"
            display = f"CVE-{cve_id}"
            ref = docutils.nodes.reference(rawtext, display, refuri=url)
            return [ref], []

        docutils.parsers.rst.roles.register_canonical_role('cve', _cve_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['cve'] = 'cve'


        # `:cwe:` → clickable CWE link
        def _cwe_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any,
                    options: Optional[Dict[str, Any]] = None,
                    content: Optional[List[str]] = None
                    ) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            cwe_num = text.strip()
            url = f"https://cwe.mitre.org/data/definitions/{cwe_num}.html"
            display = f"CWE-{cwe_num}"
            ref = docutils.nodes.reference(rawtext, display, refuri=url)
            return [ref], []

        docutils.parsers.rst.roles.register_canonical_role('cwe', _cwe_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['cwe'] = 'cwe'


        # `:pypi:` → clickable PyPI project link
        def _pypi_role(name: str, rawtext: str, text: str, lineno: int, inliner: Any,
                    options: Optional[Dict[str, Any]] = None,
                    content: Optional[List[str]] = None
                    ) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.system_message]]:
            project_name = text.strip()
            url = f"https://pypi.org/project/{project_name}/"
            display = project_name
            ref = docutils.nodes.reference(rawtext, display, refuri=url)
            return [ref], []

        docutils.parsers.rst.roles.register_canonical_role('pypi', _pypi_role)
        if hasattr(docutils.parsers.rst.languages.en, 'roles'):
            docutils.parsers.rst.languages.en.roles['pypi'] = 'pypi'

        _sphinx_roles_registered = True


class MLStripper(HTMLParser):
    """Utility class to strip out html for raw html source"""
    def __init__(self):
        super().__init__()
        self.reset()
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d: str) -> None:
        self.text.write(d)

    def get_data(self) -> str:
        return self.text.getvalue()


def strip_tags(html: str) -> str:
    s = MLStripper()
    try:
        s.feed(html)
        s.close()
    except Exception:
        return html
    return s.get_data()


# ---------------------------------------------------------------------------
# LaTeX-to-Unicode math conversion
# ---------------------------------------------------------------------------

_LATEX_TO_UNICODE = {
    # Greek lowercase
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ',
    r'\epsilon': 'ε', r'\varepsilon': 'ε', r'\zeta': 'ζ', r'\eta': 'η',
    r'\theta': 'θ', r'\vartheta': 'ϑ', r'\iota': 'ι', r'\kappa': 'κ',
    r'\lambda': 'λ', r'\mu': 'μ', r'\nu': 'ν', r'\xi': 'ξ',
    r'\pi': 'π', r'\varpi': 'ϖ', r'\rho': 'ρ', r'\varrho': 'ϱ',
    r'\sigma': 'σ', r'\varsigma': 'ς', r'\tau': 'τ', r'\upsilon': 'υ',
    r'\phi': 'φ', r'\varphi': 'φ', r'\chi': 'χ', r'\psi': 'ψ',
    r'\omega': 'ω',
    # Greek uppercase
    r'\Gamma': 'Γ', r'\Delta': 'Δ', r'\Theta': 'Θ', r'\Lambda': 'Λ',
    r'\Xi': 'Ξ', r'\Pi': 'Π', r'\Sigma': 'Σ', r'\Upsilon': 'Υ',
    r'\Phi': 'Φ', r'\Psi': 'Ψ', r'\Omega': 'Ω',
    # Operators and punctuation
    r'\times': '×', r'\div': '÷', r'\pm': '±', r'\mp': '∓',
    r'\cdot': '·', r'\ldots': '…', r'\cdots': '⋯',
    r'\vdots': '⋮', r'\ddots': '⋱',
    # Comparison
    r'\leq': '≤', r'\le': '≤', r'\geq': '≥', r'\ge': '≥',
    r'\neq': '≠', r'\ne': '≠', r'\approx': '≈', r'\equiv': '≡',
    r'\sim': '∼', r'\simeq': '≃', r'\cong': '≅', r'\propto': '∝',
    # Set operations
    r'\subset': '⊂', r'\supset': '⊃', r'\subseteq': '⊆', r'\supseteq': '⊇',
    r'\in': '∈', r'\notin': '∉', r'\cup': '∪', r'\cap': '∩',
    r'\emptyset': '∅', r'\varnothing': '∅',
    # Logic
    r'\neg': '¬', r'\wedge': '∧', r'\vee': '∨', r'\oplus': '⊕',
    r'\forall': '∀', r'\exists': '∃', r'\nexists': '∄',
    # Arrows
    r'\to': '→', r'\rightarrow': '→', r'\leftarrow': '←', r'\gets': '←',
    r'\leftrightarrow': '↔', r'\Rightarrow': '⇒', r'\Leftarrow': '⇐',
    r'\Leftrightarrow': '⇔', r'\uparrow': '↑', r'\downarrow': '↓',
    r'\updownarrow': '↕', r'\Uparrow': '⇑', r'\Downarrow': '⇓',
    r'\mapsto': '↦',
    # Miscellaneous
    r'\infty': '∞', r'\partial': '∂', r'\nabla': '∇',
    r'\sum': '∑', r'\prod': '∏', r'\int': '∫', r'\oint': '∮',
    r'\hbar': 'ℏ', r'\ell': 'ℓ', r'\wp': '℘', r'\Re': 'ℜ', r'\Im': 'ℑ',
    r'\aleph': 'ℵ', r'\angle': '∠', r'\perp': '⊥', r'\parallel': '∥',
    r'\prime': '′', r'\dagger': '†', r'\ddagger': '‡',
    r'\langle': '⟨', r'\rangle': '⟩',
    # Whitespace
    r'\quad': '  ', r'\qquad': '    ', r'\ ': ' ',
}

# Pre-sort substitutions once so repeated conversions avoid sorting overhead.
_LATEX_TO_UNICODE_SORTED = tuple(
    sorted(_LATEX_TO_UNICODE.items(), key=lambda item: -len(item[0]))
)


def _convert_math_to_unicode(text: str) -> str:
    """Convert common LaTeX math notation to Unicode approximations.

    Handles the most common cases (Greek letters, operators, arrows, etc.)
    for improved readability in the terminal.  Unknown commands are left as-is.
    """
    result = text

    # Strip \\left / \\right size modifiers (no terminal equivalent)
    result = re.sub(r'\\left\s*', '', result)
    result = re.sub(r'\\right\s*', '', result)

    # \\frac{a}{b} → (a/b)
    result = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}', r'(\1/\2)', result)

    # \\sqrt{x} → √(x)
    result = re.sub(r'\\sqrt\{([^{}]*)\}', r'√(\1)', result)

    # ^{...} → keep exponent inline
    result = re.sub(r'\^\{([^{}]*)\}', r'^\1', result)

    # _{...} → keep subscript inline
    result = re.sub(r'_\{([^{}]*)\}', r'_\1', result)

    # Remove remaining braces
    result = result.replace('{', '').replace('}', '')

    # Apply symbol substitutions (longest first to avoid partial replacements)
    for latex, uni in _LATEX_TO_UNICODE_SORTED:
        result = result.replace(latex, uni)

    return result


# pylama:ignore=D,C0116
class RSTVisitor(docutils.nodes.SparseNodeVisitor):
    """A visitor that produces rich renderables.

    .. note:: The ``_SUPERSCRIPT`` and ``_SUBSCRIPT`` translation tables are
       class-level constants so they are computed once rather than per-instance.

    Custom visitors for third-party node types can be registered via
    :meth:`register_visitor`.  Registered functions take ``(visitor, node)``
    as arguments and should follow the same conventions as the built-in
    ``visit_*`` / ``depart_*`` methods (e.g. raise
    ``docutils.nodes.SkipChildren`` to suppress child processing).
    """

    # Class-level registry mapping node_class → (visit_fn, depart_fn).
    # Entries are consulted by dispatch_visit / dispatch_departure before
    # falling through to the normal method-name lookup.
    #
    # Design note: the base class owns an empty dict.  When register_visitor is
    # called on a *subclass*, the guard below ensures the subclass gets its own
    # dict so that base-class registrations are never accidentally polluted by
    # subclass registrations (and vice-versa).  Registrations on RSTVisitor
    # itself are truly global and apply to every instance.
    _custom_visitors: ClassVar[Dict[Type[docutils.nodes.Node], Tuple[Optional[Callable[..., Any]], Optional[Callable[..., Any]]]]] = {}
    _DISPATCH_CACHE_MISS: ClassVar[object] = object()

    _SUPERSCRIPT: ClassVar[Dict[int, Union[int, str, None]]] = str.maketrans(
        "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ=+-*/×÷",
        "¹²³⁴⁵⁶⁷⁸⁹⁰ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᑫʳˢᵗᵘᵛʷˣʸᶻᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾQᴿˢᵀᵁⱽᵂˣʸᶻ⁼⁺⁻*/×÷",
    )
    _SUBSCRIPT: ClassVar[Dict[int, Union[int, str, None]]] = str.maketrans(
        "1234567890abcdefghijklmnopqrstuvwxyz=+-*/×÷", "₁₂₃₄₅₆₇₈₉₀abcdₑfgₕᵢⱼₖₗₘₙₒₚqᵣₛₜᵤᵥwₓyz₌₊₋*/×÷"
    )

    @classmethod
    def register_visitor(cls, node_class: Type[docutils.nodes.Node], visit_fn: Optional[Callable[..., Any]] = None, depart_fn: Optional[Callable[..., Any]] = None) -> Optional[Callable[..., Any]]:
        """Register custom visit/depart functions for *node_class*.

        The registration is class-wide: it applies to every instance of this
        class (and subclasses that do not provide their own registry).

        Can be used in two ways:

        **Direct form** (original API)::

            RSTVisitor.register_visitor(MyNode, visit_fn=my_visit)

        **Decorator form** (when ``visit_fn`` and ``depart_fn`` are both
        ``None``, a single-argument call returns a decorator that registers
        the decorated function as the visit handler)::

            @RSTVisitor.register_visitor(MyNode)
            def visit_my_node(visitor, node):
                visitor.renderables.append(Text(node.astext()))
                raise docutils.nodes.SkipChildren()

        Parameters
        ----------
        node_class : type
            The docutils node class to handle.
        visit_fn : callable or None
            Called as ``visit_fn(visitor, node)`` when the node is entered.
            May raise ``docutils.nodes.SkipChildren`` to suppress child
            traversal.  Pass ``None`` to use a no-op visit.
        depart_fn : callable or None
            Called as ``depart_fn(visitor, node)`` when the node is exited.
            Pass ``None`` to use a no-op departure.

        Returns
        -------
        callable or None
            When used as a decorator (no ``visit_fn`` / ``depart_fn``
            provided), returns a decorator.  Otherwise returns ``None``.
        """
        if visit_fn is None and depart_fn is None:
            # Decorator form: @RSTVisitor.register_visitor(MyNodeClass)
            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                cls.register_visitor(node_class, visit_fn=fn)
                return fn
            return _decorator

        if '_custom_visitors' not in cls.__dict__:
            # Give subclasses their own dict so parent registrations are not
            # accidentally modified.
            cls._custom_visitors = {}
        cls._custom_visitors[node_class] = (visit_fn, depart_fn)
        return None

    @classmethod
    def unregister_visitor(cls, node_class: Type[docutils.nodes.Node]) -> None:
        """Remove a previously registered custom visitor for *node_class*.

        If no registration exists for *node_class* the call is silently
        ignored.  Useful in test teardown to restore the original state.

        Parameters
        ----------
        node_class : type
            The docutils node class whose custom handlers should be removed.
        """
        if '_custom_visitors' in cls.__dict__:
            cls._custom_visitors.pop(node_class, None)

    @classmethod
    def list_registered_visitors(cls) -> Dict[Type[docutils.nodes.Node], Tuple[Optional[Callable[..., Any]], Optional[Callable[..., Any]]]]:
        """Return a snapshot of the current custom-visitor registry.

        Returns
        -------
        dict
            A ``{node_class: (visit_fn, depart_fn)}`` mapping.  The dict is
            a shallow copy; modifying it does not affect the registry.
        """
        return dict(cls._custom_visitors)

    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        entry = self._custom_visitors.get(type(node))
        if entry is not None:
            visit_fn, _ = entry
            if visit_fn is not None:
                return visit_fn(self, node)
            return None
        return self._resolve_visit_handler(type(node))(node)

    def dispatch_departure(self, node: docutils.nodes.Node) -> None:
        entry = self._custom_visitors.get(type(node))
        if entry is not None:
            _, depart_fn = entry
            if depart_fn is not None:
                return depart_fn(self, node)
            return None
        return self._resolve_depart_handler(type(node))(node)

    def __init__(
        self,
        document: docutils.nodes.document,
        console: Console,
        code_theme: Union[str, SyntaxTheme] = "monokai",
        show_line_numbers: Optional[bool] = False,
        guess_lexer: Optional[bool] = True,
        default_lexer: Optional[str] = "python",
        admonition_style: Literal["panel", "compact"] = "panel",
    ) -> None:
        super().__init__(document)
        self.console: Console = console
        self.code_theme: Union[str, SyntaxTheme] = code_theme
        self.show_line_numbers: Optional[bool] = show_line_numbers
        self.admonition_style: Literal["panel", "compact"] = admonition_style
        self.renderables: List[Any] = []
        self.errors: List[Panel] = []
        self.footer: List[Align] = []
        self.citations: List[Align] = []
        self.guess_lexer: Optional[bool] = guess_lexer
        self.default_lexer: Optional[str] = _validate_default_lexer_name(default_lexer)
        self.refname_to_renderable: Dict[str, Tuple[Text, int, int]] = {}
        # Tracks the most recent ``Text`` produced by ``depart_paragraph`` (i.e.
        # an actual prose paragraph in this visitor's scope), so that
        # ``_append_inline_to_prev_paragraph`` can distinguish a paragraph from
        # a ``Text`` emitted by some other path (admonition prefix line, body
        # paragraph from a sub-visitor, etc.) and avoid merging tags across
        # directive boundaries.
        self._last_paragraph_text: Optional[Text] = None
        # Cache node-type dispatch handlers to reduce per-node lookup cost
        # in large documents.
        self._visit_dispatch_cache: Dict[Type[docutils.nodes.Node], Callable[[docutils.nodes.Node], Any]] = {}
        self._depart_dispatch_cache: Dict[Type[docutils.nodes.Node], Callable[[docutils.nodes.Node], Any]] = {}
        self._dispatch_cache_lock = threading.Lock()

    def _resolve_visit_handler(self, node_type: Type[docutils.nodes.Node]) -> Callable[[docutils.nodes.Node], Any]:
        cached = self._visit_dispatch_cache.get(node_type, self._DISPATCH_CACHE_MISS)
        if cached is not self._DISPATCH_CACHE_MISS:
            return cached

        with self._dispatch_cache_lock:
            cached = self._visit_dispatch_cache.get(node_type, self._DISPATCH_CACHE_MISS)
            if cached is not self._DISPATCH_CACHE_MISS:
                return cached
            handler = getattr(self, f"visit_{node_type.__name__}", self.unknown_visit)
            self._visit_dispatch_cache[node_type] = handler
            return handler

    def _resolve_depart_handler(self, node_type: Type[docutils.nodes.Node]) -> Callable[[docutils.nodes.Node], Any]:
        cached = self._depart_dispatch_cache.get(node_type, self._DISPATCH_CACHE_MISS)
        if cached is not self._DISPATCH_CACHE_MISS:
            return cached

        with self._dispatch_cache_lock:
            cached = self._depart_dispatch_cache.get(node_type, self._DISPATCH_CACHE_MISS)
            if cached is not self._DISPATCH_CACHE_MISS:
                return cached
            handler = getattr(self, f"depart_{node_type.__name__}", self.unknown_departure)
            self._depart_dispatch_cache[node_type] = handler
            return handler

    def _translate_with_fallback(self, text: str, table: Dict[int, Union[int, str, None]]) -> str:
        """Translate characters using `table` while preserving unmapped/deleted chars."""
        translated_chars: List[str] = []
        for ch in text:
            mapped = table.get(ord(ch), ch)
            # str.translate deletes chars when mapping value is None; keep original instead.
            if mapped is None:
                translated_chars.append(ch)
            elif isinstance(mapped, int):
                translated_chars.append(chr(mapped))
            else:
                translated_chars.append(mapped)
        return "".join(translated_chars)

    def _guess_lexer_name(self, text: str) -> Tuple[Optional[str], bool]:
        try:
            lexer = guess_lexer(text)
        except ClassNotFound:
            return self.default_lexer, False
        guessed = lexer.aliases[0] if lexer.aliases else None
        if guessed == "text" or guessed is None:
            return self.default_lexer, False
        return guessed, True

    def _find_lexer(self, node: docutils.nodes.Node) -> Tuple[Optional[str], str]:
        lexer = (
            node["classes"][1] if len(node.get("classes")) >= 2 else (node["format"] if node.get("format") else None)
        )
        if lexer is not None:
            return lexer, "explicit"
        if self.guess_lexer:
            guessed_lexer, was_guessed = self._guess_lexer_name(node.astext())
            return guessed_lexer, "guessed" if was_guessed else "default"
        return self.default_lexer, "default"

    def _section_level(self, node: docutils.nodes.Node) -> int:
        level = 0
        parent = getattr(node, "parent", None)
        while parent is not None:
            if isinstance(parent, docutils.nodes.section):
                level += 1
            parent = getattr(parent, "parent", None)
        return level

    def _render_heading(self, text: str, level: int) -> None:
        heading_levels = [
            ("restructuredtext.title.level.1", "bold", box.DOUBLE),
            ("restructuredtext.title.level.2", "bold", box.ROUNDED),
            ("restructuredtext.title.level.3", "bold underline", None),
            ("restructuredtext.title.level.4", "bold", None),
            ("restructuredtext.title.level.5", "underline", None),
            ("restructuredtext.title.level.6", "italic", None),
        ]
        index = min(level, len(heading_levels) - 1)
        style_name, default_style, panel_box = heading_levels[index]
        style = self.console.get_style(style_name, default=default_style)
        if panel_box is None:
            self.renderables.append(Align(Text(text, style=style), "center"))
            self.renderables.append(NewLine())
        else:
            self.renderables.append(Panel(Align(Text(text, style=style), "center"), box=panel_box, style=style, border_style=style))

    def _format_labelled_node(self, node: docutils.nodes.Node) -> str:
        """Return labelled nodes (footnotes/citations) as `label: body`."""
        label_node = next((child for child in node.children if isinstance(child, docutils.nodes.label)), None)
        label = ""
        if label_node is not None:
            label = label_node.astext().replace("\n", " ").strip()

        body_parts = []
        for child in node.children:
            if child is label_node:
                continue
            part = child.astext().replace("\n", " ").strip()
            if part:
                body_parts.append(part)
        body = " ".join(body_parts).strip()

        if label and body:
            return f"{label}: {body}"
        if label:
            return f"{label}:"
        return node.astext().replace("\n", " ").strip()

    def visit_reference(self, node: docutils.nodes.Node) -> None:
        if len(node.children) == 1 and isinstance(node.children[0], docutils.nodes.image):
            return
        refuri = node.attributes.get("refuri")
        style = self.console.get_style("restructuredtext.reference", default="blue underline on default")
        if refuri:
            style = style.update_link(refuri)
        renderable = Text(node.astext().replace("\n", " "), style=style, end="")
        if self.renderables and isinstance(self.renderables[-1], Text):
            renderable.end = " "
            start = len(self.renderables[-1])
            # Calculate end based on what we're appending to avoid stale counter after merge.
            # Account for both the renderable text and its trailing space character.
            end = start + len(renderable) + len(renderable.end)
            self.renderables[-1].append_text(renderable)
        else:
            start = 0
            # Account for the trailing space character in the renderable.
            end = len(renderable) + len(renderable.end)
            self.renderables.append(renderable)

        if not refuri:
            # We'll get the URL reference later in visit_target.
            refname = node.attributes.get("refname")
            if refname:
                self.refname_to_renderable[refname] = (self.renderables[-1], start, end)
        raise docutils.nodes.SkipChildren()

    def visit_target(self, node) -> None:
        uri = node.get("refuri")
        if uri:
            for name in node["names"]:
                try:
                    renderable, start, end = self.refname_to_renderable[name]
                except KeyError:
                    continue
                style = renderable.get_style_at_offset(self.console, start)
                style = style.update_link(uri)
                renderable.stylize(style, start, end)
        raise docutils.nodes.SkipChildren()

    def visit_paragraph(self, node) -> None:
        if hasattr(node, "parent") and isinstance(node.parent, docutils.nodes.system_message):
            self.visit_system_message(node.parent)
            raise docutils.nodes.SkipChildren()

    def depart_paragraph(self, node) -> None:  # pylint: disable=unused-argument
        if self.renderables and isinstance(self.renderables[-1], Text):
            if self.renderables[-1]:
                if isinstance(getattr(node, "parent", None), docutils.nodes.list_item):
                    self.renderables[-1].append("\n")
                else:
                    self.renderables[-1].append("\n\n")
                self._last_paragraph_text = self.renderables[-1]

    def visit_title(self, node) -> None:
        level = self._section_level(node)
        self._render_heading(node.astext(), level)
        raise docutils.nodes.SkipChildren()

    def visit_subtitle(self, node) -> None:
        """Render document subtitle with ROUNDED box styling."""
        style = self.console.get_style("restructuredtext.subtitle", default="bold")
        self.renderables.append(Panel(Align(node.astext(), "center"), box=box.ROUNDED, style=style, border_style=style))
        self.renderables.append(NewLine())
        raise docutils.nodes.SkipChildren()

    def visit_rubric(self, node) -> None:
        style = self.console.get_style("restructuredtext.rubric", default="italic dim")
        self.renderables.append(Panel(Align(node.astext(), "center"), box=box.ROUNDED, style=style, border_style=style))
        raise docutils.nodes.SkipChildren()

    def visit_Text(self, node) -> None:
        style = self.console.get_style(
            "restructuredtext.text",
            default="default on default not bold not italic not underline",
        )
        if self.renderables and isinstance(self.renderables[-1], Text):
            self.renderables[-1].append_text(Text(node.astext().replace("\n", " "), style=style, end=" "))
            return
        self.renderables.append(Text(node.astext().replace("\n", " "), end="", style=style))

    def visit_comment(self, node) -> None:
        raise docutils.nodes.SkipChildren()

    def visit_substitution_definition(self, node) -> None:
        raise docutils.nodes.SkipChildren()

    def visit_compound(self, node) -> None:
        pass  # transparent container; let the visitor descend into children

    def depart_compound(self, node) -> None:  # pylint: disable=unused-argument
        pass

    def visit_container(self, node) -> None:
        # Transparent container used by ``.. container::``; traverse children.
        pass

    def depart_container(self, node) -> None:  # pylint: disable=unused-argument
        pass

    def visit_inline(self, node) -> None:
        """Render a generic inline span, applying any ``classes`` as a style name."""
        classes = node.get('classes', [])
        style_name = (
            f"restructuredtext.inline.{classes[0]}" if classes else "restructuredtext.inline"
        )
        style = self.console.get_style(style_name, default="none")
        text = node.astext().replace("\n", " ")
        self._append_inline_text(text, style)
        raise docutils.nodes.SkipChildren()

    def _append_inline_text(self, text: str, style: Style) -> None:
        """Append styled *text* to the last renderable if it is a :class:`Text`, otherwise create a new one.

        When merging into an existing Text, uses ``end=" "`` to add word
        separation; standalone Text gets ``end=""`` so the caller controls
        whitespace.
        """
        if self.renderables and isinstance(self.renderables[-1], Text):
            self.renderables[-1].append_text(Text(text, style=style, end=" "))
        else:
            self.renderables.append(Text(text, style=style, end=""))

    def _make_sub_visitor(self) -> "RSTVisitor":
        """Create a fresh sub-visitor that shares this visitor's configuration."""
        return RSTVisitor(
            self.document,
            console=self.console,
            code_theme=self.code_theme,
            show_line_numbers=self.show_line_numbers,
            guess_lexer=self.guess_lexer,
            default_lexer=self.default_lexer,
            admonition_style=self.admonition_style,
        )

    def _render_admonition_body(self, children: List[docutils.nodes.Node]) -> List[Any]:
        """Render admonition body children using a sub-visitor to preserve inline markup."""
        sub_visitor = self._make_sub_visitor()
        for child in children:
            child.walkabout(sub_visitor)
        return sub_visitor.renderables

    def _render_child_inline(self, child: docutils.nodes.Node) -> List[Any]:
        """Render a single child node using a sub-visitor to preserve inline markup.

        This is used for list items and other contexts where we want to preserve
        bold, italic, links, inline code, and other inline markup instead of
        stripping to plain text via astext().
        """
        sub_visitor = self._make_sub_visitor()
        child.walkabout(sub_visitor)
        return sub_visitor.renderables

    def _emit_admonition(
        self,
        *,
        title: str,
        glyph: str,
        style_name: str,
        default_style: str,
        body_children: List[docutils.nodes.Node],
    ) -> None:
        """Render an admonition in either ``panel`` or ``compact`` style.

        ``title`` is the bare label (e.g. ``"Note"``) — used directly as the
        panel title in panel mode and as the inline prefix label (followed by
        ``": "``) in compact mode.
        """
        style = self.console.get_style(style_name, default=default_style)
        if self.admonition_style == "compact":
            self._emit_compact_admonition(title=title, glyph=glyph, style=style, body_children=body_children)
        else:
            self._emit_panel_admonition(
                panel_title=title,
                style=style,
                body_children=body_children,
            )

    def _emit_panel_admonition(self, *, panel_title: str, style: Style, body_children: List[docutils.nodes.Node]) -> None:
        body = self._render_admonition_body(body_children)
        self.renderables.append(
            Panel(Group(*body) if body else "", title=panel_title, style=style, border_style=style)
        )

    def _emit_compact_admonition(self, *, title: str, glyph: str, style: Style, body_children: List[docutils.nodes.Node]) -> None:
        prefix = Text(f"{glyph}{title}: ", style=style, end="")
        body = self._render_admonition_body(body_children)
        self._prepend_styled_prefix(prefix, body)

    def _append_inline_to_prev_paragraph(self, tag: Text) -> None:
        """Inline ``tag`` onto the trailing paragraph, space-separated.

        Used by compact-mode version directives so that short tags like
        ``[Added in v0.47]`` share a line with the paragraph they follow,
        instead of being forced onto their own line by ``depart_paragraph``'s
        trailing ``"\\n\\n"``. Only merges when ``self.renderables[-1]`` is the
        ``Text`` most recently emitted by ``depart_paragraph`` in this
        visitor's scope (tracked via ``_last_paragraph_text``); otherwise
        falls back to emitting ``tag`` as its own paragraph. This guard
        prevents the tag from leaking onto a preceding admonition's prefix
        line or onto an admonition body paragraph appended via
        ``_prepend_styled_prefix``.
        """
        prev = self._last_paragraph_text
        if prev is not None and self.renderables and self.renderables[-1] is prev:
            prev.rstrip()
            merged = Text.assemble(prev, Text(" "), tag, end="")
            merged.append("\n\n")
            self.renderables[-1] = merged
            # Keep chained inlining working: a second version tag immediately
            # following should still be able to merge onto this same line.
            self._last_paragraph_text = merged
        else:
            tag.append("\n\n")
            self.renderables.append(tag)

    def _prepend_styled_prefix(self, prefix: Text, body: List[Any]) -> None:
        """Append ``prefix`` followed by ``body`` to ``self.renderables``.

        When the first body renderable is a :class:`Text` (the common case —
        a paragraph), the prefix is merged into it via :meth:`Text.assemble`
        so the prefix and first paragraph share a wrapped line. Otherwise
        the prefix is emitted on its own line above the body. ``prefix`` is
        expected to have ``end=""`` so paragraph spacing is governed by the
        ``"\\n\\n"`` already baked into paragraph Texts by ``depart_paragraph``.
        """
        if not body:
            prefix.append("\n\n")
            self.renderables.append(prefix)
            return
        first = body[0]
        if isinstance(first, Text):
            merged = Text.assemble(prefix, first, end=first.end)
            self.renderables.append(merged)
            self.renderables.extend(body[1:])
        else:
            self.renderables.append(prefix)
            self.renderables.extend(body)

    def _emit_version_directive(self, type_: str, version: str, body_children: List[docutils.nodes.Node]) -> None:
        style_map = {
            "versionadded": ("restructuredtext.versionadded", "bold green"),
            "versionchanged": ("restructuredtext.versionchanged", "bold cyan"),
            "deprecated": ("restructuredtext.deprecated", "bold yellow"),
            "deprecated-removed": ("restructuredtext.deprecated_removed", "bold red"),
            "availability": ("restructuredtext.availability", "bold blue"),
            "soft-deprecated": ("restructuredtext.soft_deprecated", "bold bright_yellow"),
        }
        panel_title_map = {
            "versionadded": f"New in version {version}",
            "versionchanged": f"Changed in version {version}",
            "deprecated": f"Deprecated since version {version}",
            "deprecated-removed": f"Deprecated since version {version}",
            "availability": f"Available since version {version}",
            "soft-deprecated": f"Soft Deprecated since version {version}",
        }
        # ``deprecated-removed`` relies on _DeprecatedRemovedDirective.run embedding
        # "(removed in <removed>)" into the version string, so this map produces
        # tags like ``[Deprecated in v0.9 (removed in 2.0)]``. Keep the formats
        # in sync if that directive's version-string format ever changes.
        short_title_map = {
            "versionadded": f"Added in v{version}",
            "versionchanged": f"Changed in v{version}",
            "deprecated": f"Deprecated in v{version}",
            "deprecated-removed": f"Deprecated in v{version}",
            "availability": f"Available in v{version}",
            "soft-deprecated": f"Soft Deprecated in v{version}",
        }
        # Severity glyphs match the admonition convention: ⚠ for warning-tone
        # (deprecated/soft-deprecated → yellow), ✖ for danger-tone
        # (deprecated-removed → bold red). versionadded/versionchanged/availability
        # stay glyphless.
        glyph_map = {
            "deprecated": "⚠ ",
            "deprecated-removed": "✖ ",
            "soft-deprecated": "⚠ ",
        }
        style_name, default_style = style_map.get(type_, ("restructuredtext.versionadded", "bold green"))
        style = self.console.get_style(style_name, default=default_style)

        if self.admonition_style == "panel":
            panel_title = panel_title_map.get(type_, f"{type_} {version}")
            body = self._render_admonition_body(body_children)
            self.renderables.append(
                Panel(Group(*body) if body else "", title=panel_title, style=style, border_style=style)
            )
            return

        short_title = short_title_map.get(type_, f"{type_} {version}")
        glyph = glyph_map.get(type_, "")
        body = self._render_admonition_body(body_children)
        if not body:
            tag = Text(f"{glyph}[{short_title}]", style=style, end="")
            self._append_inline_to_prev_paragraph(tag)
            return
        # Bracket-collapse only when the body is a single paragraph. Adjacent
        # paragraphs are coalesced into one trailing Text by visit_Text/depart_paragraph,
        # so detect multi-paragraph bodies by checking for an internal "\n\n".
        if len(body) == 1 and isinstance(body[0], Text):
            inner = body[0].copy()
            inner.rstrip()
            if "\n\n" not in inner.plain:
                bracketed = Text.assemble(
                    Text(f"{glyph}[{short_title}: ", style=style),
                    inner,
                    Text("]", style=style),
                    end="",
                )
                self._append_inline_to_prev_paragraph(bracketed)
                return
        # Multi-paragraph or structural body: fall back to title-prefix shape (no brackets).
        prefix = Text(f"{glyph}{short_title}: ", style=style, end="")
        self._prepend_styled_prefix(prefix, body)

    def visit_admonition(self, node) -> None:
        # Generic admonition: first child is the user-supplied title node
        if node.children and isinstance(node.children[0], docutils.nodes.title):
            user_title = node.children[0].astext()
            body_children = node.children[1:]
        else:
            user_title = "Admonition"
            body_children = node.children
        self._emit_admonition(
            title=user_title,
            glyph="",
            style_name="restructuredtext.admonition",
            default_style="bold white",
            body_children=body_children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_attention(self, node) -> None:
        self._emit_admonition(
            title="Attention",
            glyph="⚠ ",
            style_name="restructuredtext.attention",
            default_style="bold black on yellow",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_caution(self, node) -> None:
        self._emit_admonition(
            title="Caution",
            glyph="⚠ ",
            style_name="restructuredtext.caution",
            default_style="red",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_danger(self, node) -> None:
        self._emit_admonition(
            title="DANGER",
            glyph="✖ ",
            style_name="restructuredtext.danger",
            default_style="bold white on red",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_error(self, node) -> None:
        self._emit_admonition(
            title="ERROR",
            glyph="✖ ",
            style_name="restructuredtext.error",
            default_style="bold red",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_hint(self, node) -> None:
        self._emit_admonition(
            title="Hint",
            glyph="",
            style_name="restructuredtext.hint",
            default_style="yellow",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_important(self, node) -> None:
        self._emit_admonition(
            title="IMPORTANT",
            glyph="",
            style_name="restructuredtext.important",
            default_style="bold blue",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_note(self, node) -> None:
        self._emit_admonition(
            title="Note",
            glyph="",
            style_name="restructuredtext.note",
            default_style="bold white",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_tip(self, node) -> None:
        self._emit_admonition(
            title="Tip",
            glyph="",
            style_name="restructuredtext.tip",
            default_style="bold green",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_warning(self, node) -> None:
        self._emit_admonition(
            title="Warning",
            glyph="⚠ ",
            style_name="restructuredtext.warning",
            default_style="bold yellow",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def visit_versionmodified(self, node) -> None:
        type_ = node.get("type", "versionadded")
        version = node.get("version", "")
        self._emit_version_directive(type_, version, node.children)
        raise docutils.nodes.SkipChildren()

    def depart_versionmodified(self, node) -> None:
        pass

    def visit_seealso(self, node) -> None:
        self._emit_admonition(
            title="See Also",
            glyph="",
            style_name="restructuredtext.seealso",
            default_style="bold white",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def depart_seealso(self, node) -> None:
        pass

    def visit_availability(self, node) -> None:
        version = node.get("version", "")
        if version:
            self._emit_version_directive("availability", version, node.children)
        else:
            # Defensive: the directive requires a version arg, but if missing
            # we degrade to a plain admonition rather than rendering "v".
            self._emit_admonition(
                title="Availability",
                glyph="",
                style_name="restructuredtext.availability",
                default_style="bold blue",
                body_children=node.children,
            )
        raise docutils.nodes.SkipChildren()

    def depart_availability(self, node) -> None:
        pass

    def visit_soft_deprecated(self, node) -> None:
        version = node.get("version", "")
        if version:
            self._emit_version_directive("soft-deprecated", version, node.children)
        else:
            self._emit_admonition(
                title="Soft Deprecated",
                glyph="⚠ ",
                style_name="restructuredtext.soft_deprecated",
                default_style="bold bright_yellow",
                body_children=node.children,
            )
        raise docutils.nodes.SkipChildren()

    def depart_soft_deprecated(self, node) -> None:
        pass

    def visit_impl_detail(self, node) -> None:
        self._emit_admonition(
            title="Implementation Detail",
            glyph="",
            style_name="restructuredtext.impl_detail",
            default_style="bold magenta",
            body_children=node.children,
        )
        raise docutils.nodes.SkipChildren()

    def depart_impl_detail(self, node) -> None:
        pass

    def visit_centered_block(self, node) -> None:
        style = self.console.get_style("restructuredtext.centered", default="bold")
        text = node.get('text', '')
        self.renderables.append(Align(Text(text, style=style), "center"))
        raise docutils.nodes.SkipChildren()

    def depart_centered_block(self, node) -> None:
        pass

    @staticmethod
    def _parse_py_field_name(field_name: str) -> Tuple[str, str]:
        """Classify a Python-domain field-list name.

        Returns a tuple ``(kind, arg)`` where ``kind`` is one of:
        ``param``, ``type``, ``returns``, ``rtype``, ``raises``, ``unknown``.
        """
        name = field_name.strip()
        lowered = name.lower()

        if lowered in ("returns", "return"):
            return "returns", ""
        if lowered == "rtype":
            return "rtype", ""

        for prefix in ("param", "parameter", "arg", "argument"):
            token = prefix + " "
            if lowered.startswith(token):
                return "param", name[len(token):].strip()

        if lowered.startswith("type "):
            return "type", name[5:].strip()

        for prefix in ("raises", "raise", "except", "exception"):
            token = prefix + " "
            if lowered.startswith(token):
                return "raises", name[len(token):].strip()

        return "unknown", name

    def _render_py_field_list(self, field_list_node: docutils.nodes.field_list) -> List[Any]:
        """Render a Sphinx-style Python field list as API sections."""
        params = {}
        param_order = []
        returns_desc = ""
        returns_type = ""
        raises_items = []
        unknown_items = []

        for field in field_list_node.children:
            if len(field.children) < 2:
                continue
            raw_name = field.children[0].astext().strip()
            raw_value = field.children[1].astext().replace("\n", " ").strip()
            kind, arg = self._parse_py_field_name(raw_name)

            if kind == "param":
                param_name = arg or "<unnamed>"
                if param_name not in params:
                    params[param_name] = {"type": "", "desc": ""}
                    param_order.append(param_name)
                params[param_name]["desc"] = raw_value
            elif kind == "type":
                param_name = arg or "<unnamed>"
                if param_name not in params:
                    params[param_name] = {"type": "", "desc": ""}
                    param_order.append(param_name)
                params[param_name]["type"] = raw_value
            elif kind == "returns":
                returns_desc = raw_value
            elif kind == "rtype":
                returns_type = raw_value
            elif kind == "raises":
                raises_items.append((arg or "Exception", raw_value))
            else:
                unknown_items.append((raw_name, raw_value))

        if not (param_order or returns_desc or returns_type or raises_items or unknown_items):
            return self._render_admonition_body([field_list_node])

        section_style = self.console.get_style("restructuredtext.py_desc.section", default="bold")
        param_name_style = self.console.get_style("restructuredtext.py_desc.param_name", default="bold")
        param_type_style = self.console.get_style("restructuredtext.py_desc.param_type", default="cyan")
        return_style = self.console.get_style("restructuredtext.py_desc.returns", default="none")

        renderables = []

        if param_order:
            renderables.append(Text("Parameters", style=section_style))
            for param_name in param_order:
                entry = params[param_name]
                line = Text("  ")
                line.append(param_name, style=param_name_style)
                if entry["type"]:
                    line.append(": ")
                    line.append(entry["type"], style=param_type_style)
                renderables.append(line)
                if entry["desc"]:
                    renderables.append(Text(f"    {entry['desc']}"))
            renderables.append(NewLine())

        if returns_desc or returns_type:
            renderables.append(Text("Returns", style=section_style))
            if returns_type and returns_desc:
                returns_text = f"{returns_type}: {returns_desc}"
            else:
                returns_text = returns_type or returns_desc
            renderables.append(Text(f"  {returns_text}", style=return_style))
            renderables.append(NewLine())

        if raises_items:
            renderables.append(Text("Raises", style=section_style))
            for exc_name, exc_desc in raises_items:
                line = Text("  ")
                line.append(exc_name, style=param_name_style)
                if exc_desc:
                    line.append(": ")
                    line.append(exc_desc)
                renderables.append(line)
            renderables.append(NewLine())

        if unknown_items:
            renderables.append(Text("Other", style=section_style))
            for key, value in unknown_items:
                line = Text("  ")
                line.append(key, style=param_name_style)
                if value:
                    line.append(": ")
                    line.append(value)
                renderables.append(line)
            renderables.append(NewLine())

        return renderables

    def _render_py_desc_options(self, node: docutils.nodes.Node) -> List[Any]:
        """Render ``py:*`` directive options as structured metadata."""
        options = node.get('options', {}) or {}
        objtype = str(node.get("objtype", "") or "").strip().lower()
        if not options:
            return []

        label_map = {
            'value': 'Value',
            'type': 'Type',
            'module': 'Module',
            'annotation': 'Annotation',
            'canonical': 'Canonical',
            'platform': 'Platform',
            'synopsis': 'Synopsis',
        }
        flag_order = (
            'async', 'classmethod', 'staticmethod', 'abstract',
            'final', 'deprecated', 'noindex', 'no-index',
        )

        rows = []
        for key, label in label_map.items():
            value = options.get(key)
            if value is not None and value != '':
                rows.append((label, str(value)))

        flags = []
        for key in flag_order:
            if key in options:
                flags.append(key.replace('-', ' '))
        if flags:
            rows.append(('Flags', ', '.join(flags)))

        if not rows:
            return []

        section_style = self.console.get_style("restructuredtext.py_desc.section", default="bold")
        meta_name_style = self.console.get_style("restructuredtext.py_desc.meta_name", default="bold")
        meta_value_style = self.console.get_style("restructuredtext.py_desc.meta_value", default="none")

        if objtype == "data":
            renderables: List[Any] = [Text("Details", style=section_style)]
            for property_name, property_value in rows:
                line = Text("  ")
                line.append(property_name, style=meta_name_style)
                line.append(": ")
                line.append(property_value, style=meta_value_style)
                renderables.append(line)
            renderables.append(NewLine())
            return renderables

        table = Table("Property", "Value", show_lines=True)
        for property_name, property_value in rows:
            table.add_row(Text(property_name, style=meta_name_style), Text(property_value, style=meta_value_style))

        return [Text("Details", style=section_style), table, NewLine()]

    def _py_desc_panel_style(self, objtype: str, domain: str = "py") -> Style:
        """Return panel style based on object type and domain."""
        normalized_domain = (domain or "py").strip().lower()
        normalized = (objtype or "").lower().strip()
        if not normalized:
            normalized = "object"
        style_name = f"restructuredtext.{normalized_domain}_desc.{normalized}"
        if normalized_domain == "py":
            if normalized in {"class", "exception"}:
                default_style = "bold green"
            elif normalized in {"method", "classmethod", "staticmethod", "coroutinemethod", "abstractmethod"}:
                default_style = "bold cyan"
            elif normalized in {"function", "decorator", "decoratorfunction", "coroutinefunction"}:
                default_style = "bold magenta"
            elif normalized in {"attribute", "property", "data", "variable", "envvar", "option"}:
                default_style = "bold yellow"
            elif normalized in {"module", "type", "typevar", "typealias", "opcode", "describe"}:
                default_style = "bold blue"
            else:
                default_style = "bold white"
        elif normalized_domain == "c":
            if normalized in {"struct", "union", "type"}:
                default_style = "bold green"
            elif normalized in {"function", "macro"}:
                default_style = "bold magenta"
            elif normalized in {"enum", "enumerator"}:
                default_style = "bold yellow"
            elif normalized in {"member", "var"}:
                default_style = "bold cyan"
            else:
                default_style = "bold white"
        elif normalized_domain == "cpp":
            if normalized in {"class", "struct", "union", "type"}:
                default_style = "bold green"
            elif normalized in {"function", "concept"}:
                default_style = "bold magenta"
            elif normalized in {"enum", "enumerator"}:
                default_style = "bold yellow"
            elif normalized in {"member", "var"}:
                default_style = "bold cyan"
            elif normalized in {"alias"}:
                default_style = "bold blue"
            else:
                default_style = "bold white"
        elif normalized_domain == "js":
            if normalized in {"class", "module"}:
                default_style = "bold green"
            elif normalized in {"function", "method"}:
                default_style = "bold magenta"
            elif normalized in {"attribute", "data"}:
                default_style = "bold yellow"
            else:
                default_style = "bold white"
        else:
            default_style = "bold white"
        return self.console.get_style(style_name, default=default_style)

    def _highlight_c_cpp_signature(self, domain: str, objtype: str, signature: str) -> Text:
        """Apply custom syntax highlighting to C/C++ domain signatures."""
        rendered = Text(signature)
        if not signature:
            return rendered

        c_keywords = frozenset({
            "auto", "char", "const", "double", "enum", "extern", "float", "inline",
            "int", "long", "register", "restrict", "short", "signed", "static",
            "struct", "typedef", "union", "unsigned", "void", "volatile", "_Atomic",
            "_Bool", "_Complex", "_Imaginary",
        })
        cpp_keywords = frozenset({
            "bool", "char", "char8_t", "char16_t", "char32_t", "class", "concept",
            "const", "consteval", "constexpr", "constinit", "decltype", "double",
            "enum", "explicit", "export", "final", "float", "friend", "inline",
            "int", "long", "mutable", "namespace", "noexcept", "override", "private",
            "protected", "public", "short", "signed", "static", "struct", "template",
            "typename", "union", "unsigned", "using", "virtual", "void", "volatile",
            "wchar_t", "nullptr", "auto",
        })

        normalized_domain = (domain or "c").strip().lower()
        normalized_objtype = (objtype or "").strip().lower()
        type_style = self.console.get_style(f"restructuredtext.{normalized_domain}_desc.signature.type", default="bright_cyan")
        name_style = self.console.get_style(f"restructuredtext.{normalized_domain}_desc.signature.name", default="bold")
        namespace_style = self.console.get_style(f"restructuredtext.{normalized_domain}_desc.signature.namespace", default="magenta")
        operator_style = self.console.get_style(f"restructuredtext.{normalized_domain}_desc.signature.operator", default="bold yellow")
        number_style = self.console.get_style(f"restructuredtext.{normalized_domain}_desc.signature.number", default="green")

        keywords = c_keywords if normalized_domain == "c" else (c_keywords | cpp_keywords)
        keyword_pattern = r"\b(?:%s)\b" % "|".join(sorted(re.escape(keyword) for keyword in keywords))
        for match in re.finditer(keyword_pattern, signature):
            rendered.stylize(type_style, match.start(), match.end())

        for match in re.finditer(r"\b\d+(?:\.\d+)?\b", signature):
            rendered.stylize(number_style, match.start(), match.end())

        for match in re.finditer(r"::|->|=", signature):
            rendered.stylize(operator_style, match.start(), match.end())

        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)::", signature):
            rendered.stylize(namespace_style, match.start(1), match.end(1))

        if normalized_objtype == "alias":
            alias_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b\s*=", signature)
            if alias_match is not None:
                rendered.stylize(name_style, alias_match.start(1), alias_match.end(1))
        elif normalized_objtype == "function":
            name_match = None
            # Signatures may include qualified names (e.g. ``ns::Class::method(...)``);
            # the last identifier before ``(`` is the callable name to emphasize.
            for match in re.finditer(r"(~?[A-Za-z_][A-Za-z0-9_]*)\s*(?=\()", signature):
                name_match = match
            if name_match is not None:
                rendered.stylize(name_style, name_match.start(1), name_match.end(1))
        elif normalized_objtype in {"class", "struct", "union", "enum", "concept", "type"}:
            head_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*)\b", signature)
            if head_match is not None:
                leaf = head_match.group(1).split("::")[-1]
                leaf_start = head_match.end(1) - len(leaf)
                rendered.stylize(name_style, leaf_start, head_match.end(1))
        elif normalized_objtype in {"member", "var", "enumerator"}:
            rightmost_identifier = None
            for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", signature):
                token = match.group(1)
                if token not in keywords:
                    rightmost_identifier = match
            if rightmost_identifier is not None:
                rendered.stylize(name_style, rightmost_identifier.start(1), rightmost_identifier.end(1))

        return rendered

    def _highlight_js_signature(self, objtype: str, signature: str) -> Text:
        """Apply custom syntax highlighting to JavaScript-domain signatures."""
        rendered = Text(signature)
        if not signature:
            return rendered

        js_keywords = frozenset({
            "async", "await", "break", "case", "catch", "class", "const", "continue",
            "debugger", "default", "delete", "do", "else", "export", "extends",
            "false", "finally", "for", "function", "if", "import", "in", "instanceof",
            "let", "new", "null", "return", "super", "switch", "this", "throw", "true",
            "try", "typeof", "var", "void", "while", "with", "yield",
        })

        normalized_objtype = (objtype or "").strip().lower()
        keyword_style = self.console.get_style("restructuredtext.js_desc.signature.keyword", default="bright_cyan")
        name_style = self.console.get_style("restructuredtext.js_desc.signature.name", default="bold")
        namespace_style = self.console.get_style("restructuredtext.js_desc.signature.namespace", default="magenta")
        operator_style = self.console.get_style("restructuredtext.js_desc.signature.operator", default="bold yellow")
        number_style = self.console.get_style("restructuredtext.js_desc.signature.number", default="green")

        keyword_pattern = r"\b(?:%s)\b" % "|".join(sorted(re.escape(keyword) for keyword in js_keywords))
        for match in re.finditer(keyword_pattern, signature):
            rendered.stylize(keyword_style, match.start(), match.end())

        for match in re.finditer(r"\b\d+(?:\.\d+)?\b", signature):
            rendered.stylize(number_style, match.start(), match.end())

        for match in re.finditer(r"=>|=|\.", signature):
            rendered.stylize(operator_style, match.start(), match.end())

        if normalized_objtype in {"function", "method"}:
            name_match = None
            for match in re.finditer(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*(?=\()", signature):
                name_match = match
            if name_match is not None:
                rendered.stylize(name_style, name_match.start(1), name_match.end(1))
        elif normalized_objtype == "class":
            class_match = re.search(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\b", signature)
            if class_match is not None:
                rendered.stylize(name_style, class_match.start(1), class_match.end(1))
        elif normalized_objtype == "module":
            for match in re.finditer(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\.", signature):
                rendered.stylize(namespace_style, match.start(1), match.end(1))
            leaf_match = re.search(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\b$", signature)
            if leaf_match is not None:
                rendered.stylize(name_style, leaf_match.start(1), leaf_match.end(1))
        elif normalized_objtype == "attribute":
            attribute_match = re.search(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*$", signature)
            if attribute_match is not None:
                rendered.stylize(name_style, attribute_match.start(1), attribute_match.end(1))
        elif normalized_objtype == "data":
            data_match = re.search(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\b", signature)
            if data_match is not None:
                rendered.stylize(name_style, data_match.start(1), data_match.end(1))

        return rendered

    def _highlight_py_signature(self, objtype: str, signature: str) -> Text:
        """Apply custom syntax highlighting to Python-domain signatures."""
        rendered = Text(signature)
        if not signature:
            return rendered

        self_and_cls_style = self.console.get_style("restructuredtext.py_desc.signature.self_and_cls", default="bright_magenta")
        arrow_style = self.console.get_style("restructuredtext.py_desc.signature.arrow", default="bold yellow")
        type_style = self.console.get_style("restructuredtext.py_desc.signature.type", default="cyan")
        name_style = self.console.get_style("restructuredtext.py_desc.signature.name", default="bold")
        bool_style = self.console.get_style("restructuredtext.py_desc.signature.bool", default="magenta")
        int_style = self.console.get_style("restructuredtext.py_desc.signature.int", default="green")

        if objtype in {
            "function", "method", "classmethod", "staticmethod",
            "decorator", "decoratorfunction", "coroutinefunction",
            "coroutinemethod", "abstractmethod",
        }:
            name_match = None
            # Signatures may include dotted names (e.g. ``Class.method(...)``);
            # the last match before ``(`` is the callable's display name.
            for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()", signature):
                name_match = match
            if name_match is not None:
                rendered.stylize(name_style, name_match.start(1), name_match.end(1))

        for match in re.finditer(r"\b(self|cls)\b", signature):
            rendered.stylize(self_and_cls_style, match.start(1), match.end(1))

        for match in re.finditer(r"->", signature):
            rendered.stylize(arrow_style, match.start(), match.end())

        # Highlight return types, but be bracket-aware so generics like
        # ``-> dict[str, int]`` aren't cut off at internal commas.
        for arrow_match in re.finditer(r"->", signature):
            # start scanning after the arrow, skipping whitespace
            i = arrow_match.end()
            signature_length = len(signature)
            while i < signature_length and signature[i].isspace():
                i += 1
            # scan until we hit a delimiter at bracket depth 0
            depth = 0
            j = i
            while j < signature_length:
                ch = signature[j]
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    if depth > 0:
                        depth -= 1
                    else:
                        # unmatched closing - treat as delimiter
                        break
                # stop at comma, closing paren or equals only if not inside brackets
                if depth == 0 and ch in ",)=":
                    break
                j += 1
            # trim whitespace from ends
            type_start = i
            type_end = j
            while type_start < type_end and signature[type_start].isspace():
                type_start += 1
            while type_end > type_start and signature[type_end - 1].isspace():
                type_end -= 1
            if type_end > type_start:
                rendered.stylize(type_style, type_start, type_end)

        # Highlight parameter annotation types, bracket-aware so
        # ``param: dict[str, int]`` doesn't stop at the inner comma.
        for colon_match in re.finditer(r":\s*", signature):
            # start scanning at first non-space after ':'
            i = colon_match.end()
            signature_length = len(signature)
            while i < signature_length and signature[i].isspace():
                i += 1
            # if next char is ')' or ',' or end, nothing to do
            if i >= signature_length or signature[i] in ",)":
                continue
            depth = 0
            j = i
            while j < signature_length:
                ch = signature[j]
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    if depth > 0:
                        depth -= 1
                    else:
                        break
                # stop at comma, closing paren or equals only if not inside brackets
                if depth == 0 and ch in ",)=":
                    break
                j += 1
            type_start = i
            type_end = j
            while type_start < type_end and signature[type_start].isspace():
                type_start += 1
            while type_end > type_start and signature[type_end - 1].isspace():
                type_end -= 1
            if type_end > type_start:
                rendered.stylize(type_style, type_start, type_end)

        for match in re.finditer(r"\b(?:True|False)\b", signature):
            rendered.stylize(bool_style, match.start(), match.end())

        for match in re.finditer(r"\b\d+\b", signature):
            rendered.stylize(int_style, match.start(), match.end())

        return rendered

    def _render_py_desc_title(self, domain: str, objtype: str, signature: str) -> Text:
        """Render a styled panel title for Python/C/C++/JS domain objects."""
        prefix_style = self.console.get_style("restructuredtext.py_desc.title_prefix", default="bold")
        title = Text(f"[{objtype}] ", style=prefix_style)
        normalized_domain = (domain or "py").strip().lower()
        if normalized_domain in {"c", "cpp"}:
            title.append_text(self._highlight_c_cpp_signature(domain=domain, objtype=objtype, signature=signature))
        elif normalized_domain == "js":
            title.append_text(self._highlight_js_signature(objtype=objtype, signature=signature))
        else:
            title.append_text(self._highlight_py_signature(objtype=objtype, signature=signature))
        return title

    @staticmethod
    def _split_py_attribute_signature(signature: str) -> Tuple[str, str]:
        """Split ``name[: type]`` style signatures into name/type parts."""
        cleaned = signature.strip()
        if ":" in cleaned:
            name_part, _, type_part = cleaned.partition(":")
            parsed_type = type_part.strip()
        else:
            name_part = cleaned
            parsed_type = ""
        normalized_name = name_part.strip()
        # Some malformed/empty signatures can yield no usable attribute name.
        # Use a stable placeholder instead of emitting an empty attribute label.
        # Signatures may be qualified (``Class.attr``); render the leaf attribute name.
        leaf_name = normalized_name.rsplit(".", 1)[-1] if normalized_name else ""
        parsed_name = leaf_name or "<attribute>"
        return parsed_name, parsed_type

    def _collect_typed_class_attributes(self, class_node: docutils.nodes.Node) -> Tuple[List[Tuple[str, str, str]], List[docutils.nodes.Node]]:
        """Collect typed ``py:attribute`` style children under a class description."""
        attributes: List[Tuple[str, str, str]] = []
        remaining_children: List[docutils.nodes.Node] = []
        attribute_types = {"attribute", "property", "data", "variable"}

        for child in class_node.children:
            if isinstance(child, py_desc) and child.get("objtype", "").lower() in attribute_types:
                child_options = child.get("options", {}) or {}
                attr_name, sig_type = self._split_py_attribute_signature(child.get("sig", ""))
                raw_type = child_options.get("type")
                if raw_type in (None, ""):
                    raw_type = sig_type
                attr_type = str(raw_type).strip() if raw_type is not None else ""
                if attr_type:
                    description_parts = []
                    for grandchild in child.children:
                        # Field lists are rendered separately by _render_py_field_list
                        # and should not be duplicated in attribute descriptions.
                        if isinstance(grandchild, docutils.nodes.field_list):
                            continue
                        piece = grandchild.astext().replace("\n", " ").strip()
                        if piece:
                            description_parts.append(piece)
                    attributes.append((attr_name, attr_type, " ".join(description_parts).strip()))
                    continue
            remaining_children.append(child)

        return attributes, remaining_children

    def _render_py_class_attribute_table(self, rows: List[Tuple[str, str, str]]) -> List[Any]:
        """Render typed class attributes as an indented list."""
        section_style = self.console.get_style("restructuredtext.py_desc.section", default="bold")
        name_style = self.console.get_style("restructuredtext.py_desc.param_name", default="bold")
        type_style = self.console.get_style("restructuredtext.py_desc.param_type", default="cyan")
        value_style = self.console.get_style("restructuredtext.py_desc.meta_value", default="none")

        renderables: List[Any] = [Text("Attributes", style=section_style)]
        for attr_name, attr_type, attr_description in rows:
            attr_text = Text(attr_name, style=name_style)
            attr_text.append(": ")
            attr_text.append(attr_type, style=type_style)
            line = Text("  ")
            line.append_text(attr_text)
            renderables.append(line)
            if attr_description:
                renderables.append(Text(f"    {attr_description}", style=value_style))
        renderables.append(NewLine())
        return renderables

    def visit_py_desc(self, node) -> None:
        domain = node.get('domain', 'py')
        objtype = node.get('objtype', 'object')
        sig = node.get('sig', '')
        style = self._py_desc_panel_style(objtype, domain=domain)
        title = self._render_py_desc_title(domain=domain, objtype=objtype, signature=sig)
        body = []
        body_children: List[docutils.nodes.Node]

        if domain == "py" and objtype in {"class", "exception"}:
            typed_attributes, body_children = self._collect_typed_class_attributes(node)
            if typed_attributes:
                body.extend(self._render_py_class_attribute_table(typed_attributes))
        else:
            body_children = list(node.children)

        body.extend(self._render_py_desc_options(node))
        for child in body_children:
            if isinstance(child, docutils.nodes.field_list):
                body.extend(self._render_py_field_list(child))
            else:
                body.extend(self._render_admonition_body([child]))
        self.renderables.append(
            Panel(Group(*body) if body else "", title=title,
                  style=style, border_style=style)
        )
        raise docutils.nodes.SkipChildren()

    def depart_py_desc(self, node) -> None:
        pass

    def visit_toctree_stub(self, node) -> None:
        style = self.console.get_style("restructuredtext.toctree", default="bold cyan")
        caption = node.get('caption', 'Contents')
        entries = list(node.get('entries', []))
        maxdepth = node.get('maxdepth', 0)  # 0 means unlimited
        reversed_entries = node.get('reversed', False)
        numbered_enabled = node.get('numbered_enabled', False)
        numbered_depth = node.get('numbered', 0)
        marker_style = self.console.get_style("restructuredtext.bullet_list_marker", default="bold yellow")

        if reversed_entries:
            entries.reverse()

        renderables = []
        counters: List[int] = []
        for entry in entries:
            if not entry:
                continue
            # Parse the optional "Display Title <docname>" format.
            if entry.endswith('>') and '<' in entry:
                display = entry[:entry.rfind('<')].strip()
                docname = entry[entry.rfind('<') + 1:-1].strip()
            else:
                display = entry
                docname = entry

            # Derive visual depth from the number of '/' separators in the
            # document name so that entries like "guide/installation" appear
            # indented under their parent path group.
            depth = docname.count('/')
            if maxdepth > 0 and depth >= maxdepth:
                continue  # Omit entries beyond the configured maxdepth.

            if numbered_enabled:
                if depth >= len(counters):
                    counters.extend([0] * (depth + 1 - len(counters)))
                else:
                    counters = counters[:depth + 1]
                counters[depth] += 1

            if numbered_enabled and (numbered_depth == 0 or depth < numbered_depth):
                number_label = ".".join(str(value) for value in counters[:depth + 1])
                marker = "  " * depth + f"{number_label}. "
            else:
                markers = [" • ", " ∘ ", " ▪ "]
                marker = "  " * depth + markers[min(depth, len(markers) - 1)]
            renderables.append(Text(marker + display, style=marker_style))

        self.renderables.append(
            Panel(Group(*renderables) if renderables else "", title=caption,
                  style=style, border_style=style)
        )
        raise docutils.nodes.SkipChildren()

    def depart_toctree_stub(self, node) -> None:
        pass

    def visit_literalinclude_stub(self, node) -> None:
        style = self.console.get_style("restructuredtext.literalinclude", default="grey58")
        filename = node.get('filename', '<unknown file>')
        content = node.get('content', None)

        if content is not None:
            # File was successfully read by the directive — render as a syntax-
            # highlighted code block with the filename as the panel title.
            language = node.get('language') or self.default_lexer
            linenos = node.get('linenos', self.show_line_numbers)
            self.renderables.append(
                Panel(
                    Syntax(content, language, theme=self.code_theme, line_numbers=linenos),
                    title=filename,
                    border_style=style,
                    box=box.SQUARE,
                )
            )
        else:
            # File was not available (wrong path, no source file, …): show a
            # placeholder panel so the document still renders without crashing.
            self.renderables.append(
                Panel(Text(filename), title="literalinclude", border_style=style)
            )
        raise docutils.nodes.SkipChildren()

    def depart_literalinclude_stub(self, node) -> None:
        pass

    def visit_glossary_block(self, node) -> None:
        style = self.console.get_style("restructuredtext.glossary", default="bold")
        body = self._render_admonition_body(node.children)
        self.renderables.append(
            Panel(Group(*body) if body else "", title="Glossary", style=style, border_style=style)
        )
        raise docutils.nodes.SkipChildren()

    def depart_glossary_block(self, node) -> None:
        pass

    def visit_hlist_block(self, node) -> None:
        """Render an hlist node as a borderless multi-column table."""
        columns = node.get('columns', 2) or 2

        # Collect all list items from the nested bullet_list
        items = []
        for child in node.children:
            if isinstance(child, docutils.nodes.bullet_list):
                for item in child.children:
                    item_renderables = self._render_admonition_body(item.children)
                    if not item_renderables:
                        items.append(Text(""))
                    elif len(item_renderables) == 1:
                        items.append(item_renderables[0])
                    else:
                        items.append(Group(*item_renderables))

        if not items:
            raise docutils.nodes.SkipChildren()

        hlist_table = Table(show_header=False, box=None, padding=(0, 1))
        for _ in range(columns):
            hlist_table.add_column("")

        # Distribute items row-major
        for row_start in range(0, len(items), columns):
            row = list(items[row_start:row_start + columns])
            while len(row) < columns:
                row.append(Text(""))
            hlist_table.add_row(*row)

        self.renderables.append(hlist_table)
        raise docutils.nodes.SkipChildren()

    def depart_hlist_block(self, node) -> None:
        pass

    def visit_subscript(self, node) -> None:
        style = self.console.get_style("restructuredtext.subscript", default="none")
        translated = self._translate_with_fallback(node.astext(), self._SUBSCRIPT)
        self._append_inline_text(translated, style)
        raise docutils.nodes.SkipChildren()

    def visit_superscript(self, node) -> None:
        style = self.console.get_style("restructuredtext.superscript", default="none")
        translated = self._translate_with_fallback(node.astext(), self._SUPERSCRIPT)
        self._append_inline_text(translated, style)
        raise docutils.nodes.SkipChildren()

    def visit_emphasis(self, node) -> None:
        style = self.console.get_style("restructuredtext.emphasis", default="italic")
        self._append_inline_text(node.astext().replace("\n", " "), style)
        raise docutils.nodes.SkipChildren()

    def visit_strong(self, node) -> None:
        style = self.console.get_style("restructuredtext.strong", default="bold")
        self._append_inline_text(node.astext().replace("\n", " "), style)
        raise docutils.nodes.SkipChildren()

    def _make_image_text(self, node: docutils.nodes.image, link_override: Optional[str] = None) -> Text:
        alt, target = None, None
        if ":target:" in node.rawsource:
            target = node.rawsource.split(":target:")[-1].strip()
        if ":alt:" in node.rawsource:
            alt = node.rawsource.split(":alt:")[-1].strip()
        link = link_override or node.get("target", target or "Image") or node.get("uri")
        return Text("🌆 ") + Text(
            node.get("alt", alt or "Image"),
            style=Style(link=link, color="#6088ff"),
        )


    def _render_inline_with_explanation(self, node: docutils.nodes.Node, style_name: str) -> None:
        style = self.console.get_style(style_name, default="underline")
        explanation = node.get("explanation", "")
        text = node.astext().replace("\n", " ")
        if explanation:
            text = f"{text} ({explanation})"
        self._append_inline_text(text, style)
        raise docutils.nodes.SkipChildren()


    def visit_abbreviation(self, node) -> None:
        self._render_inline_with_explanation(node, "restructuredtext.abbreviation")


    def visit_acronym(self, node) -> None:
        self._render_inline_with_explanation(node, "restructuredtext.acronym")


    def visit_image(self, node) -> None:
        self.renderables.append(self._make_image_text(node))
        raise docutils.nodes.SkipChildren()

    def visit_figure(self, node) -> None:
        # When :target: is given, docutils wraps the image in a reference node
        ref_node = next((c for c in node.children if isinstance(c, docutils.nodes.reference)), None)
        image_node = next((c for c in node.children if isinstance(c, docutils.nodes.image)), None)
        if image_node is None and ref_node is not None:
            image_node = next((c for c in ref_node.children if isinstance(c, docutils.nodes.image)), None)
        caption_node = next((c for c in node.children if isinstance(c, docutils.nodes.caption)), None)
        legend_node = next((c for c in node.children if isinstance(c, docutils.nodes.legend)), None)

        if image_node is not None:
            link_override = ref_node.get("refuri") if ref_node is not None else None
            image_text = self._make_image_text(image_node, link_override=link_override)
        else:
            image_text = Text("🌆 Image")
        caption = caption_node.astext() if caption_node is not None else None
        legend_text = legend_node.astext().replace("\n", " ") if legend_node is not None else None

        border_style = self.console.get_style("restructuredtext.figure_border", default="blue")
        legend_style = self.console.get_style("restructuredtext.figure_legend", default="dim")
        body_renderable = (
            Group(image_text, Text(legend_text, style=legend_style))
            if legend_text is not None
            else image_text
        )
        # Render legend inside the body so it can wrap naturally instead of
        # being cropped in a one-line subtitle slot.
        self.renderables.append(Panel(body_renderable, title=caption, border_style=border_style, expand=False))
        raise docutils.nodes.SkipChildren()

    _BULLET_LIST_MARKERS = [" • ", " ∘ ", " ▪ "]

    @staticmethod
    def _merge_bullet_markers_with_text(renderables: List[Any]) -> List[Any]:
        """Merge marker-only bullet Text nodes with their following Text node.

        List rendering emits the marker and item body as separate Text
        renderables. In contexts that prefix each renderable line-by-line
        (e.g. block quotes), that separation can visually split bullets from
        their text. This helper keeps marker and first text fragment together.
        """
        merged = []
        i = 0
        bullet_markers = {"•", "∘", "▪"}
        while i < len(renderables):
            current = renderables[i]
            if (
                isinstance(current, Text)
                and current.plain.strip() in bullet_markers
                and i + 1 < len(renderables)
                and isinstance(renderables[i + 1], Text)
            ):
                combined = Text()
                combined.append_text(current)
                combined.append_text(renderables[i + 1])
                merged.append(combined)
                i += 2
                continue

            merged.append(current)
            i += 1

        return merged

    def _render_bullet_list(self, node: docutils.nodes.bullet_list, level: int = 0) -> None:
        """Recursively render a bullet list with support for unlimited nesting and any child elements."""
        marker_style = self.console.get_style("restructuredtext.bullet_list_marker", default="bold yellow")
        text_style = self.console.get_style("restructuredtext.bullet_list_text", default="none")
        indent = "  " * level
        marker = self._BULLET_LIST_MARKERS[min(level, len(self._BULLET_LIST_MARKERS) - 1)]
        for list_item in node.children:
            first_content = True
            for child in list_item.children:
                if isinstance(child, docutils.nodes.bullet_list):
                    self._render_bullet_list(child, level + 1)
                elif isinstance(child, docutils.nodes.enumerated_list):
                    self._render_enumerated_list(child, level + 1)
                elif isinstance(child, docutils.nodes.literal_block):
                    if first_content:
                        self.renderables.append(Text(indent + marker, end="", style=marker_style))
                        first_content = False
                    try:
                        self.visit_literal_block(child)
                    except docutils.nodes.SkipChildren:
                        pass
                else:
                    # Use sub-visitor to preserve inline markup (bold, italic, links, etc.)
                    child_renderables = self._render_child_inline(child)
                    if first_content:
                        # Prepend the marker directly onto the first Text
                        # renderable so they form a single unit.  When rendered
                        # inside a Table.grid() cell, separate renderables are
                        # laid out independently, which would put the marker
                        # and its text on different lines.
                        if child_renderables and isinstance(child_renderables[0], Text):
                            combined = Text(indent + marker, end="", style=marker_style)
                            combined.append_text(child_renderables[0])
                            child_renderables[0] = combined
                            self.renderables.extend(child_renderables)
                        else:
                            self.renderables.append(Text(indent + marker, end="", style=marker_style))
                            self.renderables.extend(child_renderables)
                        first_content = False
                    else:
                        # Prepend continuation indent to first renderable if it's text
                        if child_renderables:
                            if isinstance(child_renderables[0], Text):
                                child_renderables[0].stylize(text_style)
                            self.renderables.extend(child_renderables)

    def visit_bullet_list(self, node) -> None:
        self._render_bullet_list(node, level=0)
        self.renderables.append(NewLine())
        raise docutils.nodes.SkipChildren()

    @staticmethod
    def _make_enum_marker(enumtype: str, i: int) -> str:
        """Convert an integer *i* to the appropriate enumeration label."""
        from rich_rst._vendor.docutils.utils._roman_numerals import RomanNumeral
        if enumtype == "loweralpha":
            return chr(ord("a") + i - 1)
        elif enumtype == "upperalpha":
            return chr(ord("A") + i - 1)
        elif enumtype == "lowerroman":
            return str(RomanNumeral(i)).lower()
        elif enumtype == "upperroman":
            return str(RomanNumeral(i))
        else:  # arabic (default)
            return str(i)

    def _render_enumerated_list(self, node: docutils.nodes.enumerated_list, level: int = 0) -> None:
        """Recursively render an enumerated list with support for unlimited nesting and any child elements."""
        marker_style = self.console.get_style("restructuredtext.enumerated_list_marker", default="bold yellow")
        text_style = self.console.get_style("restructuredtext.enumerated_text", default="none")
        indent = "  " * level
        enumtype = node.get("enumtype", "arabic")
        prefix = node.get("prefix", "")
        suffix = node.get("suffix", ".")
        start = node.get("start", 1)
        for idx, list_item in enumerate(node.children):
            i = start + idx
            marker = f"{indent} {prefix}{self._make_enum_marker(enumtype, i)}{suffix}"
            first_content = True
            for child in list_item.children:
                if isinstance(child, docutils.nodes.bullet_list):
                    self._render_bullet_list(child, level + 1)
                elif isinstance(child, docutils.nodes.enumerated_list):
                    self._render_enumerated_list(child, level + 1)
                elif isinstance(child, docutils.nodes.literal_block):
                    if first_content:
                        self.renderables.append(Text(marker, end=" ", style=marker_style))
                        first_content = False
                    try:
                        self.visit_literal_block(child)
                    except docutils.nodes.SkipChildren:
                        pass
                else:
                    # Use sub-visitor to preserve inline markup (bold, italic, links, etc.)
                    child_renderables = self._render_child_inline(child)
                    if first_content:
                        self.renderables.append(Text(marker, end=" ", style=marker_style))
                        self.renderables.extend(child_renderables)
                        first_content = False
                    else:
                        # Prepend continuation indent to first renderable if it's text
                        if child_renderables:
                            if isinstance(child_renderables[0], Text):
                                child_renderables[0].stylize(text_style)
                            self.renderables.extend(child_renderables)

    def visit_enumerated_list(self, node) -> None:
        self._render_enumerated_list(node, level=0)
        self.renderables.append(NewLine())
        raise docutils.nodes.SkipChildren()

    def visit_literal(self, node) -> None:
        style = self.console.get_style("restructuredtext.inline_codeblock", default="grey78 on grey7")
        self._append_inline_text(node.astext().replace("\n", " "), style)
        raise docutils.nodes.SkipChildren()

    def visit_title_reference(self, node) -> None:
        style = self.console.get_style("restructuredtext.title_reference", default="italic")
        self._append_inline_text(node.astext().replace("\n", " "), style)
        raise docutils.nodes.SkipChildren()

    def visit_literal_block(self, node) -> None:
        style = self.console.get_style("restructuredtext.literal_block_border", default="grey58")
        if self.renderables and isinstance(self.renderables[-1], Text):
            self.renderables[-1].rstrip()
            self.renderables[-1].append_text(Text("\n"))
        lexer, lexer_source = self._find_lexer(node)
        title = lexer if lexer_source == "explicit" else f"{lexer} ({lexer_source})"
        # If the directive supplied a :name: option, include it in the
        # panel title alongside the language identifier.
        name = node.get('name')
        if name:
            title = f"{title} — {name}"

        # Determine whether to show line numbers. We show them when:
        # - the directive explicitly requested `:linenos:`, or
        # - there are highlighted lines, or
        # - the global `show_line_numbers` is enabled.
        has_highlight = bool(node.get('highlight_lines'))
        explicit_linenos = bool(node.get('linenos', False))
        show_linenos = explicit_linenos or has_highlight or self.show_line_numbers

        start_line = int(node.get('start_line', 1))

        self.renderables.append(
            Panel(
                Syntax(
                    node.astext(),
                    lexer,
                    theme=self.code_theme,
                    line_numbers=show_linenos,
                    start_line=start_line,
                    highlight_lines=node.get('highlight_lines'),
                ),
                border_style=style,
                box=box.SQUARE,
                title=title,
            )
        )
        raise docutils.nodes.SkipChildren()

    def visit_system_message(self, node) -> None:
        self.errors.append(
            Panel(
                Text(node.astext()),
                title=f"System Message: {node.attributes.get('type', '?')}/{node.attributes.get('level', '?')} ({node.attributes.get('source', '?')}, line {node.attributes.get('line', '?')});",
                border_style={None: "none", "INFO": "bold cyan", "WARNING": "bold yellow", "ERROR": "bold red", "SEVERE": "bold magenta", "DEBUG": "bold white"}.get(
                    node.attributes.get("type"), "bold red"
                )
            ),
        )

        # Preserve the offending source snippet in normal output so invalid
        # markup does not silently disappear when show_errors=False.
        # Skip snippets for title formatting errors where the title was already parsed correctly.
        message_text = node.astext().lower()
        is_title_error = any(keyword in message_text for keyword in ("title", "overline", "underline"))
        
        if not is_title_error:
            for child in node.children:
                if isinstance(child, docutils.nodes.literal_block):
                    snippet = child.astext().replace("\n", " ")
                    if snippet:
                        if self.renderables and isinstance(self.renderables[-1], Text):
                            self.renderables[-1].append_text(Text(snippet, end=" "))
                        else:
                            self.renderables.append(Text(snippet, end=""))
        raise docutils.nodes.SkipChildren()

    def _add_to_field_table(self, field_name: str, field_value: str) -> None:
        """Add a row to the shared field table, creating it if necessary."""
        field_name_style = self.console.get_style("restructuredtext.field_name", default="bold")
        field_value_style = self.console.get_style("restructuredtext.field_value", default="none")
        if self.renderables and isinstance(self.renderables[-1], Table):
            possible_table = self.renderables[-1]
            if (possible_table.columns[0].header == "Field Name") and (possible_table.columns[1].header == "Field Value"):
                possible_table.add_row(Text(field_name, style=field_name_style), Text(field_value, style=field_value_style))
                return
        table = Table("Field Name", "Field Value", show_lines=True)
        table.add_row(Text(field_name, style=field_name_style), Text(field_value, style=field_value_style))
        self.renderables.append(table)

    def visit_field(self, node) -> None:
        self._add_to_field_table(node.children[0].astext(), node.children[1].astext())
        raise docutils.nodes.SkipChildren()

    def visit_docinfo(self, node) -> None:
        pass  # let the visitor descend into child docinfo nodes

    def visit_author(self, node) -> None:
        self._add_to_field_table("Author", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_authors(self, node) -> None:
        for author in node.children:
            self._add_to_field_table("Author", author.astext())
        raise docutils.nodes.SkipChildren()

    def visit_organization(self, node) -> None:
        self._add_to_field_table("Organization", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_address(self, node) -> None:
        self._add_to_field_table("Address", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_contact(self, node) -> None:
        self._add_to_field_table("Contact", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_version(self, node) -> None:
        self._add_to_field_table("Version", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_revision(self, node) -> None:
        self._add_to_field_table("Revision", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_status(self, node) -> None:
        self._add_to_field_table("Status", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_date(self, node) -> None:
        self._add_to_field_table("Date", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_copyright(self, node) -> None:
        self._add_to_field_table("Copyright", node.astext())
        raise docutils.nodes.SkipChildren()

    def visit_definition_list(self, node) -> None:
        term_style = self.console.get_style("restructuredtext.term_style", default="none")
        classifier_style = self.console.get_style("restructuredtext.classifier_style", default="cyan")
        definitions_style = self.console.get_style("restructuredtext.definitions_style", default="none")
        for child in node.children:
            child_children = child.children
            if not child_children:
                continue

            if len(child_children) == 3:
                # term + one classifier + definition
                term, classifier, definitions = child_children[:3]
                header = (
                    Text(term.astext(), style=term_style, end="")
                    + Text(" : ", end="")
                    + Text(classifier.astext(), style=classifier_style)
                )
                self.renderables.append(header)
                self.renderables.append(Text("\n    ", end=""))
                # Use a sub-visitor so inline markup inside the definition body
                # (bold, italic, links, etc.) is preserved rather than flattened.
                def_renderables = self._render_admonition_body(
                    definitions.children if hasattr(definitions, 'children') else []
                )
                self.renderables.extend(def_renderables)
                self.renderables.append(Text("\n", end=""))
            elif len(child_children) >= 2:
                term = child_children[0]
                # The last child is always the definition; everything between
                # term and definition are additional classifiers.
                definition = child_children[-1]
                if len(child_children) > 2:
                    # Render the first classifier (child_children[1]) as part of
                    # the term header, and handle any extra classifiers plus the
                    # definition body.
                    first_classifier = child_children[1]
                    header = (
                        Text(term.astext(), style=term_style, end="")
                        + Text(" : ", end="")
                        + Text(first_classifier.astext(), style=classifier_style)
                    )
                    self.renderables.append(header)
                    for ch in child_children[2:]:
                        if isinstance(ch, docutils.nodes.classifier):
                            self.renderables.append(
                                Text(" : " + ch.astext(), style=classifier_style)
                            )
                        elif isinstance(ch, docutils.nodes.definition):
                            self.renderables.append(Text("\n    ", end=""))
                            def_renderables = self._render_admonition_body(ch.children)
                            self.renderables.extend(def_renderables)
                            self.renderables.append(Text("\n", end=""))
                        elif isinstance(ch, docutils.nodes.paragraph):
                            self.renderables.append(Text("\n    ", end=""))
                            self.renderables.extend(self._render_child_inline(ch))
                            self.renderables.append(Text("\n", end=""))
                        elif isinstance(ch, docutils.nodes.bullet_list):
                            try:
                                self.visit_bullet_list(ch)
                            except docutils.nodes.SkipChildren:
                                pass
                        elif isinstance(ch, docutils.nodes.enumerated_list):
                            try:
                                self.visit_enumerated_list(ch)
                            except docutils.nodes.SkipChildren:
                                pass
                        elif isinstance(ch, docutils.nodes.literal_block):
                            try:
                                self.visit_literal_block(ch)
                            except docutils.nodes.SkipChildren:
                                pass
                        elif isinstance(ch, docutils.nodes.literal):
                            try:
                                self.visit_literal(ch)
                            except docutils.nodes.SkipChildren:
                                pass
                        elif isinstance(ch, docutils.nodes.block_quote):
                            try:
                                self.visit_block_quote(ch)
                            except docutils.nodes.SkipChildren:
                                pass
                else:
                    # len == 2: term + definition (no classifier).
                    # Rename clarity: `definition` is child_children[1], NOT a
                    # classifier — the old variable name was misleading.
                    self.renderables.append(
                        Text(term.astext(), style=term_style)
                        + Text("\n    ", end="")
                        + Text(definition.astext().replace("\n", " "), style=definitions_style)
                        + Text("\n      ", end="")
                    )
            else:
                term = child_children[0]
                self.renderables.append(Text(term.astext(), style=term_style) + Text("\n", end=""))
        raise docutils.nodes.SkipChildren()

    def visit_option_list(self, node) -> None:
        option_string_style = self.console.get_style("restructuredtext.option_string", default="none")
        option_argument_style = self.console.get_style("restructuredtext.option_argument", default="none")
        option_child_text_separator_style = self.console.get_style(
            "restructuredtext.option_child_text_separator", default="none"
        )
        option_description_style = self.console.get_style("restructuredtext.option_description", default="none")
        for option_list_item in node.children:
            option_group, description = option_list_item.children
            # option_group.child_text_separator.join(map(lambda x: x.astext(), option_group.children)))
            option_text = Text(end="")
            for option in option_group.children:
                try:
                    option_string, option_argument = option.children
                except ValueError:
                    option_string, option_argument = option.children[0], None
                option_text += (
                    Text(option_string.astext(), style=option_string_style)
                    + (Text(option_argument.astext(), style=option_argument_style) if option_argument else Text())
                    + (
                        Text(option_group.child_text_separator, style=option_child_text_separator_style)
                        if len(option_group.children) > 1
                        else Text()
                    )
                )
            if description:
                option_text += Text("\n    ")
                option_text += Text(description.astext(), style=option_description_style)
            self.renderables.append(option_text + Text("\n"))
        raise docutils.nodes.SkipChildren()

    def visit_doctest_block(self, node) -> None:
        style = self.console.get_style("restructuredtext.literal_block_border", default="grey58")
        self.renderables.append(
            Panel(
                Syntax(node.astext(), "pycon", theme=self.code_theme, line_numbers=self.show_line_numbers),
                border_style=style,
                box=box.SQUARE,
                title="doctest block",
            )
        )
        raise docutils.nodes.SkipChildren()

    def visit_block_quote(self, node) -> None:
        text_style = self.console.get_style("restructuredtext.blockquote_text", default="white")
        marker_style = self.console.get_style(
            "restructuredtext.blockquote_attribution_marker", default="bright_magenta"
        )
        author_style = self.console.get_style("restructuredtext.blockquote_attribution_text", default="grey89")
        children = list(node.children)
        attribution = children[-1] if children and isinstance(children[-1], docutils.nodes.attribution) else None
        paragraphs = children[:-1] if attribution else children

        for index, paragraph in enumerate(paragraphs):
            if index:
                self.renderables.append(NewLine())
                self.renderables.append(NewLine())
            # Use a sub-visitor so inline markup (bold, italic, links, …)
            # inside the paragraph is preserved instead of being flattened by
            # astext().
            para_renderables = self._render_child_inline(paragraph)
            para_renderables = self._merge_bullet_markers_with_text(para_renderables)
            if para_renderables and isinstance(para_renderables[0], Text):
                first = para_renderables[0]
                first.rstrip()
                # Apply the block-quote body style so tests that check for a
                # white span still find one.
                first.stylize(text_style, 0, len(first))
                combined = Text("▌ ", style=marker_style)
                combined.append_text(first)
                self.renderables.append(combined)
                # Prepend the same `▌ ` marker to every subsequent Text so
                # that deeply nested block quotes accumulate the correct number
                # of markers at every nesting level.
                for r in para_renderables[1:]:
                    if isinstance(r, Text):
                        combined_r = Text("▌ ", style=marker_style)
                        combined_r.append_text(r)
                        self.renderables.append(combined_r)
                    else:
                        self.renderables.append(r)
            else:
                self.renderables.append(Text("▌ ", style=marker_style))
                self.renderables.extend(para_renderables)

        if attribution:
            self.renderables.append(NewLine())
            self.renderables.append(
                Text("  \u2014 " + attribution.astext(), style=author_style)
            )
        else:
            self.renderables.append(NewLine())

        raise docutils.nodes.SkipChildren()

    def _render_line_block(self, node: docutils.nodes.line_block, indent: int = 0) -> None:
        """Recursively render a line_block node, preserving nested indentation."""
        prefix = "    " * indent
        for child in node.children:
            if isinstance(child, docutils.nodes.line_block):
                self._render_line_block(child, indent + 1)
            elif isinstance(child, docutils.nodes.line):
                self.renderables.append(Text(prefix + child.astext()))

    def visit_line_block(self, node) -> None:
        self._render_line_block(node)
        raise docutils.nodes.SkipChildren()

    def _collect_body_renderables(self, children: List[docutils.nodes.Node]) -> List[Any]:
        """Render a list of body nodes into renderables, returning the collected list.

        Uses a sub-visitor for each child so that inline markup (bold, italic,
        links, inline code, etc.) is preserved throughout.
        """
        result = []
        for child in children:
            result.extend(self._render_child_inline(child))
        return result

    def visit_topic(self, node) -> None:
        style = self.console.get_style("restructuredtext.topic", default="bold cyan")
        children = list(node.children)
        title = ""
        body_start = 0
        if children and isinstance(children[0], docutils.nodes.title):
            title = children[0].astext()
            body_start = 1

        body_renderables = self._collect_body_renderables(children[body_start:])

        if body_renderables:
            self.renderables.append(
                Panel(Group(*body_renderables), title=title, style=style, border_style=style)
            )
        else:
            self.renderables.append(Panel("", title=title, style=style, border_style=style))
        raise docutils.nodes.SkipChildren()

    def visit_sidebar(self, node) -> None:
        children = list(node.children)
        title = ""
        body_children = children

        if body_children and isinstance(body_children[0], docutils.nodes.title):
            title = body_children[0].astext()
            body_children = body_children[1:]

        subtitle = ""
        if body_children and isinstance(body_children[0], docutils.nodes.subtitle):
            subtitle = body_children[0].astext()
            body_children = body_children[1:]

        # Use _collect_body_renderables so inline markup in the sidebar body is
        # preserved instead of being flattened by astext().
        body_renderables = self._collect_body_renderables(body_children)
        content = Group(*body_renderables) if body_renderables else ""
        self.renderables.append(Panel(content, title=title, subtitle=subtitle, expand=False))

        raise docutils.nodes.SkipChildren()

    def visit_transition(self, node) -> None:
        style = self.console.get_style("restructuredtext.hr", default="yellow")
        self.renderables.append(Rule(style=style))

    def visit_math_block(self, node) -> None:
        style = self.console.get_style("restructuredtext.literal_block_border", default="grey58")
        if self.renderables and isinstance(self.renderables[-1], Text):
            self.renderables[-1].rstrip()
            self.renderables[-1].append_text(Text("\n"))
        converted = _convert_math_to_unicode(node.astext())
        self.renderables.append(
            Panel(
                Text(converted),
                border_style=style,
                box=box.SQUARE,
                title="math",
            )
        )
        raise docutils.nodes.SkipChildren()

    def visit_math(self, node) -> None:
        """Render inline math with Unicode approximations where possible."""
        style = self.console.get_style("restructuredtext.math", default="italic")
        converted = _convert_math_to_unicode(node.astext().replace("\n", " "))
        self._append_inline_text(converted, style)
        raise docutils.nodes.SkipChildren()

    def visit_citation(self, node) -> None:
        self.citations.append(Align(self._format_labelled_node(node), "left"))
        raise docutils.nodes.SkipChildren()

    def visit_citation_reference(self, node) -> None:
        style = self.console.get_style("restructuredtext.citation_reference", default="grey74")
        if self.renderables and isinstance(self.renderables[-1], Text):
            self.renderables[-1].append(node.astext().replace("\n", " "), style=style)
            raise docutils.nodes.SkipChildren()
        self.renderables.append(Text(node.astext().replace("\n", " "), style=style, end=""))
        raise docutils.nodes.SkipChildren()

    def visit_header(self, node) -> None:
        style = self.console.get_style("restructuredtext.caption", default="bold")
        self.renderables.insert(0, Panel(Align(node.astext(), "center"), title="caption", box=box.DOUBLE, style=style))
        raise docutils.nodes.SkipChildren()

    def visit_footer(self, node) -> None:
        self.footer.append(Align(node.astext(), "center"))
        raise docutils.nodes.SkipChildren()

    def visit_footnote_reference(self, node) -> None:
        style = self.console.get_style("restructuredtext.footnote_reference", default="grey74")
        newline = '\n'
        text = f"[{node.astext().replace(newline, ' ')}]"
        if self.renderables and isinstance(self.renderables[-1], Text):
            self.renderables[-1].append(text, style=style)
            raise docutils.nodes.SkipChildren()
        self.renderables.append(Text(text, style=style, end=""))
        raise docutils.nodes.SkipChildren()

    def visit_substitution_reference(self, node) -> None:
        style = self.console.get_style("restructuredtext.substitution_reference", default="none")
        text = node.astext().replace("\n", " ")
        if self.renderables and isinstance(self.renderables[-1], Text):
            self.renderables[-1].append(text, style=style)
            raise docutils.nodes.SkipChildren()
        self.renderables.append(Text(text, style=style, end=""))
        raise docutils.nodes.SkipChildren()

    def visit_footnote(self, node) -> None:
        self.footer.append(Align(self._format_labelled_node(node), "left"))
        raise docutils.nodes.SkipChildren()

    def visit_generated(self, node) -> None:
        self.footer.append(Align(node.astext(), "left"))
        raise docutils.nodes.SkipChildren()

    def visit_pending(self, node) -> None:
        raise docutils.nodes.SkipChildren()

    def visit__colSpan(self, node) -> None:
        raise docutils.nodes.SkipNode()

    def visit__rowSpan(self, node) -> None:
        raise docutils.nodes.SkipNode()

    def visit_problematic(self, node) -> None:
        # Keep problematic inline source visible in the main render output.
        problematic_style = self.console.get_style("restructuredtext.problematic", default="none")
        problematic_text = node.astext().replace("\n", " ")
        if problematic_text:
            if self.renderables and isinstance(self.renderables[-1], Text):
                self.renderables[-1].append(problematic_text, style=problematic_style)
            else:
                self.renderables.append(Text(problematic_text, style=problematic_style, end=""))

        self.errors.append(
            Panel(
                Syntax(node.astext(), lexer="rst", theme=self.code_theme),
                title=f"System Message: Problematic Element",
                border_style="bold red",
            ),
        )
        raise docutils.nodes.SkipChildren()

    def visit_raw(self, node) -> None:
        style = self.console.get_style("restructuredtext.literal_block_border", default="grey58")
        lexer, _ = self._find_lexer(node)
        text = node.astext()
        title = ("stripped raw html" if lexer == "html" else "raw " + lexer)

        if lexer == "html":
            text = strip_tags(text)
            # Stripping HTML tags leaves behind plain text
            lexer = None

        self.renderables.append(
            Panel(
                Syntax(text, lexer, theme=self.code_theme, line_numbers=self.show_line_numbers),
                border_style=style,
                box=box.SQUARE,
                title=title,
            )
        )
        raise docutils.nodes.SkipChildren()

    # ── spanning table renderer ───────────────────────────────────────────────

    @staticmethod
    def _spanning_table(
        grid: List[List[Any]],
        col_widths: List[int],
        header_rows: int,
        title: Optional[str],
        header_style: Any,
        cell_style: Any,
        console: Console,
    ) -> "Group":
        """Build a Rich Group that renders a table with proper cspan/rspan merging.

        *grid[r][c]* is either ``(renderable, cspan, rspan)`` for a real cell or
        ``None`` for a placeholder occupied by a span from another cell.
        *col_widths[c]* is the inner character width of column *c* (excluding borders).
        """
        nrows = len(grid)
        ncols = len(col_widths)
        lines: List[Text] = []

        # ── box chars ──────────────────────────────────────────────────────
        # Top border (heavy)
        TL, TH, TM, TR = "┏", "━", "┳", "┓"
        # Head/body separator
        SL, SH, SM, SR = "┡", "━", "╇", "┩"
        # Body row separator
        ML, MH, MM, MR = "├", "─", "┼", "┤"
        # Bottom border
        BL, BH, BM, BR = "└", "─", "┴", "┘"
        # Vertical content borders: header uses heavy ┃, body uses light │
        VH, VB = "┃", "│"

        # ── helpers ────────────────────────────────────────────────────────
        origin_cache: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}

        def _origin(r: int, c: int) -> Optional[Tuple[int, int]]:
            """Return (origin_row, origin_col) for the real cell covering (r, c)."""
            key = (r, c)
            cached = origin_cache.get(key, None)
            if cached is not None or key in origin_cache:
                return cached

            for rr in range(r, -1, -1):
                for cc in range(c, -1, -1):
                    cell = grid[rr][cc]
                    if cell is None:
                        continue
                    _, csp, rsp = cell
                    if rr <= r <= rr + rsp and cc <= c <= cc + csp:
                        origin_cache[key] = (rr, cc)
                        return (rr, cc)

            origin_cache[key] = None
            return None

        def _rspan_continues(row_above: int, c: int) -> bool:
            """True if a cell covering (row_above, c) extends to the next row."""
            if row_above < 0 or row_above + 1 >= nrows:
                return False
            for rr in range(row_above, -1, -1):
                for cc in range(c, -1, -1):
                    cell = grid[rr][cc]
                    if cell is None:
                        continue
                    _, csp, rsp = cell
                    if cc <= c <= cc + csp and rr <= row_above <= rr + rsp:
                        return row_above < rr + rsp
            return False

        def _cspan_continues(r: int, c: int) -> bool:
            """True if column c is a cspan continuation of the cell to its left in row r."""
            if c == 0:
                return False
            left_origin = _origin(r, c - 1)
            here_origin = _origin(r, c)
            return left_origin is not None and left_origin == here_origin

        def _is_header(r: int) -> bool:
            return r < header_rows

        def _has_vborder(r: int, c: int) -> bool:
            """True iff row *r* has a vertical separator between column *c* and *c+1*."""
            return _origin(r, c) != _origin(r, c + 1)

        def _segments_to_lines(line_segments: List[Segment]) -> List[Text]:
            lines: List[Text] = [Text()]
            for seg in line_segments:
                if seg.control or not seg.text:
                    continue
                parts = seg.text.split("\n")
                for index, part in enumerate(parts):
                    if part:
                        lines[-1].append(part, seg.style)
                    if index < len(parts) - 1:
                        lines.append(Text())
            return lines

        def _row_style(r: int) -> Any:
            return header_style if _is_header(r) else cell_style

        cell_render_cache: Dict[Tuple[int, int], List[Text]] = {}

        def _render_cell_lines(r: int, c: int) -> List[Text]:
            """Render cell content into styled lines sized to its spanned width."""
            key = (r, c)
            if key in cell_render_cache:
                return cell_render_cache[key]

            cell = grid[r][c]
            if cell is None:
                cell_render_cache[key] = []
                return []

            content, csp, _ = cell
            avail = sum(col_widths[c:c + csp + 1]) + 3 * csp
            style = _row_style(r)
            if avail <= 0:
                cell_render_cache[key] = [Text("")]
                return cell_render_cache[key]

            options = console.options.update(width=avail, max_width=avail)
            render_target = Styled(content, style) if style else (content if content is not None else Text(""))
            rendered_lines = console.render_lines(
                render_target,
                options=options,
                style=None,
                pad=True,
                new_lines=False,
            )

            lines: List[Text] = []
            for rendered in rendered_lines:
                lines.extend(_segments_to_lines(rendered))
            if not lines:
                lines = [Text(" " * avail, style=style)]
            normalized: List[Text] = []
            for line in lines:
                current_width = cell_len(line.plain)
                if current_width > avail:
                    line.truncate(avail, overflow="crop", pad=False)
                elif current_width < avail:
                    line.append(" " * (avail - current_width), style=style)
                normalized.append(line)

            cell_render_cache[key] = normalized
            return normalized

        # ── separator line ─────────────────────────────────────────────────

        def _sep(above: Optional[int], below: Optional[int]) -> Text:
            """Horizontal rule between rows *above* and *below* (None = table edge)."""
            is_top = above is None
            is_bot = below is None
            is_head_sep = (
                above is not None
                and below is not None
                and above == header_rows - 1
                and below == header_rows
            )
            # Separator between two header rows (not the final header→body boundary).
            is_inner_header_sep = (
                above is not None
                and below is not None
                and _is_header(above)
                and _is_header(below)
            )
            if is_top:
                L, H, M, R = TL, TH, TM, TR
            elif is_bot:
                L, H, M, R = BL, BH, BM, BR
            elif is_head_sep:
                L, H, M, R = SL, SH, SM, SR
            elif is_inner_header_sep:
                L, H, M, R = "┣", "━", "╋", "┫"
            else:
                L, H, M, R = ML, MH, MM, MR

            # Left border: use heavy ┃ inside header, light │ in body, for rspan continuations
            rc0 = _rspan_continues(above, 0) if above is not None and not is_top else False
            V_sep = VH if is_inner_header_sep else VB
            if rc0 and not is_top and not is_bot:
                s = V_sep
            else:
                s = L
            for c in range(ncols):
                rc = _rspan_continues(above, c) if above is not None and not is_top else False
                if rc:
                    s += " " * (col_widths[c] + 2)
                else:
                    s += H * (col_widths[c] + 2)

                if c < ncols - 1:
                    lrc = rc
                    rrc = (_rspan_continues(above, c + 1) if above is not None and not is_top else False)
                    if lrc and rrc:
                        same_origin = (
                            above is not None
                            and _origin(above, c) is not None
                            and _origin(above, c) == _origin(above, c + 1)
                        )
                        # When both columns continue the same merged rowspan cell,
                        # there is no interior boundary at this separator.
                        s += " " if same_origin else V_sep
                    elif lrc or rrc:
                        if is_inner_header_sep:
                            s += "┣" if lrc else "┫"
                        else:
                            s += "├" if lrc else "┤"
                    else:
                        has_up = above is not None and not is_top and _has_vborder(above, c)
                        has_dn = below is not None and _has_vborder(below, c)
                        if has_up and has_dn:
                            if is_head_sep:
                                s += SM
                            elif is_inner_header_sep:
                                s += "╋"
                            else:
                                s += MM
                        elif has_up:
                            # ┻ = heavy horizontal + upward arm (head sep and inner header)
                            s += "┻" if (is_head_sep or is_inner_header_sep) else BM
                        elif has_dn:
                            # ┯/┳ = heavy horizontal + downward arm
                            if is_top:
                                s += TM
                            elif is_head_sep:
                                s += "┯"
                            elif is_inner_header_sep:
                                s += "┳"
                            else:
                                s += "┬"
                        else:
                            s += H  # no junction — just continue horizontal line
            # Right border
            rcN = _rspan_continues(above, ncols - 1) if above is not None and not is_top else False
            if rcN and not is_top and not is_bot:
                s += V_sep
            else:
                s += R
            return Text(s)

        # ── content line ───────────────────────────────────────────────────

        def _row_height(r: int) -> int:
            """Physical line count for a logical row after rendering cell content."""
            height = 1
            c = 0
            while c < ncols:
                if _cspan_continues(r, c):
                    c += 1
                    continue
                cell = grid[r][c]
                if cell is None:
                    c += 1
                    continue
                _, csp, _ = cell
                height = max(height, len(_render_cell_lines(r, c)))
                c += 1 + csp
            return height

        def _content(r: int, line_no: int) -> Text:
            """One physical content line for logical row *r*."""
            is_hdr = _is_header(r)
            V = VH if is_hdr else VB
            style = _row_style(r)
            line = Text(V)
            c = 0
            while c < ncols:
                if _cspan_continues(r, c):
                    # Part of a spanning cell rendered by a previous column.
                    c += 1
                    continue

                cell = grid[r][c]
                if cell is not None:
                    content, csp, _ = cell
                    avail = sum(col_widths[c:c + csp + 1]) + 3 * csp
                    rendered = _render_cell_lines(r, c)
                    inner = rendered[line_no] if line_no < len(rendered) else Text(" " * avail, style=style)
                    line.append(" ", style=style)
                    line.append_text(inner)
                    line.append(" ", style=style)
                    if c + csp < ncols - 1:
                        line.append(V)
                    c += 1 + csp  # jump past all placeholder columns
                else:
                    # Placeholder covered by a rowspan from an origin above.
                    # If this column is the first covered column for that origin
                    # in this row, render the full merged placeholder width.
                    origin = _origin(r, c)
                    if origin is not None and origin[1] == c:
                        span_end = c
                        while span_end + 1 < ncols and _origin(r, span_end + 1) == origin:
                            span_end += 1
                        csp = span_end - c
                        avail = sum(col_widths[c:span_end + 1]) + 3 * csp
                        line.append(" " * (avail + 2), style=style)
                        if span_end < ncols - 1:
                            line.append(V)
                        c = span_end + 1
                    else:
                        line.append(" " * (col_widths[c] + 2), style=style)
                        if c < ncols - 1 and not _cspan_continues(r, c + 1):
                            line.append(V)
                        c += 1
            line.append(V)
            return line

        def _is_placeholder_row(r: int) -> bool:
            """True when a row is fully covered by rowspans from above."""
            c = 0
            while c < ncols:
                if _cspan_continues(r, c):
                    c += 1
                    continue
                if grid[r][c] is not None:
                    return False
                if _origin(r, c) is None:
                    return False
                c += 1
            return True

        # ── assemble lines ─────────────────────────────────────────────────

        if title:
            total = cell_len(_sep(None, 0).plain) if nrows else (sum(col_widths) + 3 * ncols + 1)
            lines.append(Text(title.center(total), style="italic"))

        for r in range(nrows):
            above = r - 1 if r > 0 else None
            is_placeholder = _is_placeholder_row(r)
            sep_line = _sep(above, r)
            if not (is_placeholder and all(ch in f" {VB}{VH}" for ch in sep_line.plain)):
                lines.append(sep_line)
            if is_placeholder:
                continue
            for line_no in range(_row_height(r)):
                lines.append(_content(r, line_no))

        lines.append(_sep(nrows - 1, None))
        return Group(*lines)

    # ── table visitor ─────────────────────────────────────────────────────

    def visit_table(self, node) -> None:
        header_style = self.console.get_style("restructuredtext.table_header", default="bold")
        cell_style = self.console.get_style("restructuredtext.table_cell", default="none")

        # Extract optional caption/title and the tgroup
        title = None
        tgroup = None
        for child in node.children:
            if isinstance(child, (docutils.nodes.title, docutils.nodes.caption)):
                title = child.astext()
            elif isinstance(child, docutils.nodes.tgroup):
                tgroup = child

        if tgroup is None:
            raise docutils.nodes.SkipChildren()

        # Count total columns from colspec elements (authoritative column count)
        num_cols = sum(1 for c in tgroup.children if isinstance(c, docutils.nodes.colspec))

        # Find thead and tbody within tgroup
        thead = None
        tbody = None
        for child in tgroup.children:
            if isinstance(child, docutils.nodes.thead):
                thead = child
            elif isinstance(child, docutils.nodes.tbody):
                tbody = child

        if tbody is None:
            raise docutils.nodes.SkipChildren()

        # Fallback column count when colspec elements are absent
        if num_cols == 0:
            if thead is not None and thead.children:
                num_cols = sum(1 + e.get("morecols", 0) for e in thead.children[0].children)
            elif tbody.children:
                num_cols = sum(1 + e.get("morecols", 0) for e in tbody.children[0].children)

        def _render_entry_content(entry: docutils.nodes.Node) -> Any:
            """Render an entry node with a sub-visitor to preserve inline RST markup."""
            sub_visitor = self._make_sub_visitor()
            for child in entry.children:
                child.walkabout(sub_visitor)
            renderables = sub_visitor.renderables
            if not renderables:
                return Text("", style=cell_style)
            has_list = any(
                isinstance(child, (docutils.nodes.bullet_list, docutils.nodes.enumerated_list))
                for child in entry.children
            )
            if has_list:
                # Table cells should keep list items compact: one visible line
                # per item without paragraph/list trailing blank lines.
                renderables = self._merge_bullet_markers_with_text(renderables)
                renderables = [r for r in renderables if not isinstance(r, NewLine)]
                if not renderables:
                    return Text("", style=cell_style)
                rendered_lines = self.console.render_lines(
                    Group(*renderables),
                    options=self.console.options.update(width=2048, max_width=2048),
                    pad=False,
                    new_lines=False,
                )
                compact_lines: List[Text] = []
                for line in rendered_lines:
                    line_text = Text.assemble(
                        *[(seg.text, seg.style) for seg in line if not seg.control]
                    )
                    line_text.rstrip()
                    if line_text.plain.strip():
                        compact_lines.append(line_text)
                if not compact_lines:
                    return Text("", style=cell_style)
                if len(compact_lines) == 1:
                    return compact_lines[0]
                return Group(*compact_lines)
            # depart_paragraph appends "\n\n" to trailing Text renderables; strip
            # it so cells don't carry extra vertical whitespace.  Also strip any
            # leading whitespace left over after span-role nodes (:cspan:/:rspan:)
            # are removed (the space between the role and the following text is
            # preserved as a leading space in the text node).
            for i, r in enumerate(renderables):
                if isinstance(r, Text):
                    r.rstrip()
                    leading = len(r.plain) - len(r.plain.lstrip())
                    if leading:
                        trimmed = r[leading:]
                        trimmed.end = r.end
                        renderables[i] = trimmed
            if len(renderables) == 1:
                return renderables[0]
            return Group(*renderables)

        def _build_row_cells(row: docutils.nodes.Node, occupied_cols: set) -> Tuple[List[Any], Dict[int, int]]:
            """Build cell renderables for one body row.

            Accounts for columns already occupied by rowspans from earlier rows
            and for cells that span multiple columns (morecols).  Returns a tuple
            of (cells, new_rowspans) where new_rowspans maps col_idx to the
            morerows value for any spanning cells introduced by this row.
            """
            cells = []
            new_rowspans = {}
            col_idx = 0
            entry_iter = iter(row.children)

            while col_idx < num_cols:
                if col_idx in occupied_cols:
                    # Column is covered by a rowspan from a previous row
                    cells.append(Text("", style=cell_style))
                    col_idx += 1
                    continue

                entry = next(entry_iter, None)
                if entry is None:
                    # All entries for this row have been consumed; pad remaining
                    # columns with empty cells (can happen with complex spanning).
                    cells.append(Text("", style=cell_style))
                    col_idx += 1
                    continue

                morecols = entry.get("morecols", 0)
                morerows = entry.get("morerows", 0)

                cells.append(_render_entry_content(entry))

                # Record any new rowspan introduced by this cell
                if morerows > 0:
                    for span_col in range(col_idx, col_idx + 1 + morecols):
                        new_rowspans[span_col] = morerows

                # Pad empty cells for additional spanned columns (colspan)
                for _ in range(morecols):
                    cells.append(Text("", style=cell_style))

                col_idx += 1 + morecols

            return cells, new_rowspans

        # ── detect whether any cell carries a span ────────────────────────────
        def _any_spans(section: docutils.nodes.Node) -> bool:
            for row in section.children:
                for e in row.children:
                    if e.get("morecols", 0) or e.get("morerows", 0):
                        return True
            return False

        has_spans = _any_spans(tbody) or (thead is not None and _any_spans(thead))

        if has_spans:
            # ── build a logical grid for the spanning renderer ────────────────
            num_header_rows = len(thead.children) if thead else 0
            grid: List[List[Any]] = []
            # rspan_active[col] = remaining body rows this col is still occupied
            rspan_active: Dict[int, int] = {}

            all_rows: List[Tuple[docutils.nodes.Node, bool]] = []
            if thead:
                for row in thead.children:
                    all_rows.append((row, True))
            for row in tbody.children:
                all_rows.append((row, False))

            for row_node, _ in all_rows:
                grid_row: List[Any] = [None] * num_cols
                col = 0
                entry_iter = iter(row_node.children)
                while col < num_cols:
                    if col in rspan_active:
                        rspan_active[col] -= 1
                        if rspan_active[col] <= 0:
                            del rspan_active[col]
                        col += 1
                        continue
                    entry = next(entry_iter, None)
                    if entry is None:
                        col += 1
                        continue
                    mc = entry.get("morecols", 0)
                    mr = entry.get("morerows", 0)
                    content = _render_entry_content(entry)
                    grid_row[col] = (content, mc, mr)
                    if mr > 0:
                        for span_c in range(col, col + mc + 1):
                            rspan_active[span_c] = mr
                    col += 1 + mc
                grid.append(grid_row)

            # ── calculate column widths from non-spanning cells ───────────────
            # Per-table-call cache; dropped after this visit_table invocation.
            # Keep identity pairs instead of id(...) keys so reuse of object ids
            # can never return stale data.
            rendered_plain_lines_cache: List[Tuple[Any, List[str]]] = []

            def _rendered_plain_lines(renderable: Any) -> List[str]:
                if renderable is None:
                    return []
                for cached_renderable, cached_lines in rendered_plain_lines_cache:
                    if cached_renderable is renderable:
                        return cached_lines
                lines = self.console.render_lines(
                    renderable,
                    options=self.console.options.update(width=2048, max_width=2048),
                    pad=False,
                    new_lines=False,
                )
                plain_lines: List[str] = []
                for line in lines:
                    plain = "".join(seg.text for seg in line if not seg.control)
                    plain_lines.append(plain)
                rendered_plain_lines_cache.append((renderable, plain_lines))
                return plain_lines

            def _plain_w(renderable: Any) -> int:
                lines = _rendered_plain_lines(renderable)
                return max((cell_len(line) for line in lines), default=0)

            def _min_token_w(renderable: Any) -> int:
                lines = _rendered_plain_lines(renderable)
                widest = 1
                for line in lines:
                    for token in line.split():
                        widest = max(widest, cell_len(token))
                return min(20, widest)

            col_widths = [1] * num_cols
            col_min_widths = [1] * num_cols
            for grid_row in grid:
                for c, cell in enumerate(grid_row):
                    if cell is None:
                        continue
                    content, mc, mr = cell
                    if mc == 0:
                        col_widths[c] = max(col_widths[c], _plain_w(content))
                        col_min_widths[c] = max(col_min_widths[c], _min_token_w(content))

            # Widen for spanning cells that need more space
            for grid_row in grid:
                for c, cell in enumerate(grid_row):
                    if cell is None:
                        continue
                    content, mc, mr = cell
                    if mc > 0:
                        available = sum(col_widths[c:c + mc + 1]) + 3 * mc
                        needed = _plain_w(content)
                        if needed > available:
                            col_widths[c + mc] += needed - available

            # Clamp spanning-table width to the available console width so long
            # text wraps inside cells instead of producing overflow and broken
            # visual alignment in narrow terminals.
            max_total_width = max(1, self.console.options.max_width)

            def _table_width(widths: List[int]) -> int:
                return sum(widths) + 3 * len(widths) + 1

            overflow = _table_width(col_widths) - max_total_width

            def _shrink_to_floor(floors: List[int], remaining: int) -> int:
                while remaining > 0:
                    reducible = [i for i, w in enumerate(col_widths) if w > floors[i]]
                    if not reducible:
                        break
                    reducible.sort(key=lambda i: col_widths[i], reverse=True)
                    per_col_cut = max(1, remaining // len(reducible))
                    changed = 0
                    for idx in reducible:
                        if remaining <= 0:
                            break
                        max_cut = col_widths[idx] - floors[idx]
                        cut = min(max_cut, per_col_cut, remaining)
                        if cut <= 0:
                            continue
                        col_widths[idx] -= cut
                        remaining -= cut
                        changed += cut
                    if changed == 0:
                        break
                return remaining

            # Prefer preserving enough width to avoid one-character vertical
            # stacks in key columns, then fall back to absolute minimum when
            # terminal width is very constrained.
            overflow = _shrink_to_floor(col_min_widths, overflow)
            if overflow > 0:
                overflow = _shrink_to_floor([1] * num_cols, overflow)

            self.renderables.append(
                self._spanning_table(
                    grid, col_widths, num_header_rows,
                    title, header_style, cell_style,
                    self.console,
                )
            )
            raise docutils.nodes.SkipChildren()

        # ── no spans: use Rich Table for best formatting ──────────────────────
        has_header = thead is not None and bool(thead.children)
        rich_table = Table(
            show_header=has_header,
            title=title,
            header_style=header_style,
            show_lines=True,
        )

        if thead is not None and thead.children:
            header_row = thead.children[0]
            col_idx = 0
            for entry in header_row.children:
                morecols = entry.get("morecols", 0)
                rich_table.add_column(entry.astext().replace("\n", " ").strip(), style=cell_style)
                for _ in range(morecols):
                    rich_table.add_column("", style=cell_style)
                col_idx += 1 + morecols
            while col_idx < num_cols:
                rich_table.add_column("", style=cell_style)
                col_idx += 1
        else:
            for _ in range(num_cols):
                rich_table.add_column("", style=cell_style)

        rowspan_remaining: Dict[int, int] = {}
        for row in tbody.children:
            occupied = {col for col, rem in rowspan_remaining.items() if rem > 0}
            cells, new_rowspans = _build_row_cells(row, occupied)
            for col in list(occupied):
                rowspan_remaining[col] -= 1
                if rowspan_remaining[col] <= 0:
                    del rowspan_remaining[col]
            rowspan_remaining.update(new_rowspans)
            rich_table.add_row(*cells)

        self.renderables.append(rich_table)
        raise docutils.nodes.SkipChildren()


class RestructuredText(JupyterMixin):
    """A reStructuredText renderable for rich.

    Parameters
    ----------
    markup : str
        A string containing reStructuredText markup.
    code_theme : Optional[Union[str, SyntaxTheme]]
        Pygments theme for code blocks. Defaults to "monokai".
    show_line_numbers : Optional[bool]
        Whether to display line numbers for syntax-highlighted code blocks.
    show_errors : Optional[bool]
        Whether to show system_messages aka errors and warnings.
    guess_lexer : Optional[bool]
        Whether to guess lexers for code blocks without specified language.
    default_lexer : Optional[str]
        Which lexer to use if no lexer is guessed or found. Defaults to "python"
    sphinx_compat : Optional[bool]
        Enable compatibility with Sphinx roles (func, meth, class, etc.) commonly used in
        Python docstrings. When enabled, these roles render as inline code instead of errors.
        Defaults to True for better compatibility with Python documentation.
    filename : Optional[str]
        A file name to use for error messages, useful for debugging purposes. Defaults to "<rst-document>"
    admonition_style : str
        How admonition directives (``note``, ``warning``, ``versionadded``, etc.) render.
        ``"panel"`` (default) emits a bordered Rich :class:`~rich.panel.Panel` per directive.
        ``"compact"`` collapses each directive to a styled inline title prefix, making the
        output suitable for narrow contexts such as CLI ``--help`` panels.
    """

    def __init__(
        self,
        markup: str,
        code_theme: Optional[Union[str, SyntaxTheme]] = "monokai",
        show_line_numbers: Optional[bool] = False,
        show_errors: Optional[bool] = False,
        guess_lexer: Optional[bool] = False,
        default_lexer: Optional[str] = "python",
        sphinx_compat: Optional[bool] = True,
        filename: Optional[str] = "<rst-document>",
        admonition_style: Literal["panel", "compact"] = "panel",
    ) -> None:
        if admonition_style not in ("panel", "compact"):
            raise ValueError(
                f"admonition_style must be 'panel' or 'compact', got {admonition_style!r}"
            )
        self.markup: str = markup
        self.code_theme: Optional[Union[str, SyntaxTheme]] = code_theme
        self.show_line_numbers: Optional[bool] = show_line_numbers
        self.show_errors: Optional[bool] = show_errors
        self.guess_lexer: Optional[bool] = guess_lexer
        self.default_lexer: Optional[str] = _validate_default_lexer_name(default_lexer)
        self.sphinx_compat: Optional[bool] = sphinx_compat
        self.filename: Optional[str] = filename
        self.admonition_style: Literal["panel", "compact"] = admonition_style

    def render_to_string(self, width: Optional[int] = None, *, force_terminal: bool = False) -> str:
        """Render the RST markup to a plain string.

        This is a convenience wrapper around the full rich rendering pipeline.
        All options passed to the constructor (code theme, show_errors, etc.)
        are respected.

        Parameters
        ----------
        width : int, optional
            Output width in columns.  Defaults to 80 when not specified.
        force_terminal : bool, optional
            When ``True`` the console is created with ``force_terminal=True``,
            which enables ANSI styles in the exported text.  Defaults to
            ``False`` so that the plain-text output is style-free by default.

        Returns
        -------
        str
            The rendered markup as a plain string.
        """
        console = Console(
            width=width or 80,
            force_terminal=force_terminal,
            record=True,
        )
        console.print(self)
        return console.export_text()

    def render_to_html(
        self,
        width: Optional[int] = None,
        *,
        theme: Optional[TerminalTheme] = None,
    ) -> str:
        """Render the RST markup to an HTML string.

        Parameters
        ----------
        width : int, optional
            Output width in columns.  Defaults to 80.
        theme : rich.terminal_theme.TerminalTheme, optional
            The colour theme to use for the HTML export.  Defaults to
            ``DEFAULT_TERMINAL_THEME`` from :mod:`rich.terminal_theme`.

        Returns
        -------
        str
            A self-contained HTML document.
        """
        console = Console(width=width or 80, force_terminal=True, record=True)
        console.print(self)
        return console.export_html(theme=theme or DEFAULT_TERMINAL_THEME)

    def render_to_svg(
        self,
        width: Optional[int] = None,
        *,
        title: str = "",
    ) -> str:
        """Render the RST markup to an SVG string.

        Parameters
        ----------
        width : int, optional
            Output width in columns.  Defaults to 80.
        title : str, optional
            Title shown in the SVG image header.  Defaults to an empty string.

        Returns
        -------
        str
            An SVG document as a string.
        """
        console = Console(width=width or 80, force_terminal=True, record=True)
        console.print(self)
        return console.export_svg(title=title)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        if self.sphinx_compat:
            _register_sphinx_roles()
            _register_sphinx_directives()

        # Use the full docutils publish pipeline so that all standard transforms
        # (substitution resolution, hyperlink resolution, footnote numbering,
        # bibliographic-field promotion, …) are applied before we walk the tree.
        document = docutils.core.publish_doctree(
            self.markup,
            source_path=self.filename,
            settings_overrides={"report_level": 69, "halt_level": 69},
        )

        # Render the RST `document` using Rich.
        visitor = RSTVisitor(
            document,
            console=console,
            code_theme=self.code_theme,
            show_line_numbers=self.show_line_numbers,
            guess_lexer=self.guess_lexer,
            default_lexer=self.default_lexer,
            admonition_style=self.admonition_style,
        )
        document.walkabout(visitor)

        # Strip all trailing newlines and newline-like rich objects
        while visitor.renderables:
            if isinstance(visitor.renderables[-1], Text):
                visitor.renderables[-1].rstrip()
                visitor.renderables[-1].end = "\n"
                if visitor.renderables[-1]:  # The Text object still contains data.
                    break
                else:
                    visitor.renderables.pop()
            elif isinstance(visitor.renderables[-1], NewLine):
                visitor.renderables.pop()
            else:
                break

        for renderable in visitor.renderables:
            # Move trailing "\n"s from Text content into ``end``. Otherwise a
            # paragraph stored as ``Text("X\n\n", end="")`` renders to three
            # padded lines under ``options.justify == "left"`` — the content
            # plus two phantom blank-padded rows — and the trailing padded
            # blank fuses onto the next renderable's first row, breaking
            # callers like cyclopts' help-cell layout. Visible output is
            # identical when trailing newlines live in ``end`` instead.
            if isinstance(renderable, Text):
                plain = renderable.plain
                if plain.endswith("\n"):
                    stripped = plain.rstrip("\n")
                    trailing = plain[len(stripped):]
                    fixed = renderable.copy()
                    fixed.rstrip()
                    fixed.end = trailing + fixed.end
                    renderable = fixed
            yield from console.render(renderable, options)
        if self.show_errors and visitor.errors:
            for error in visitor.errors:
                yield from console.render(error, options)

        citation_style = console.get_style("restructuredtext.citation", default="none")
        citation_border_style = console.get_style("restructuredtext.citation_border", default="grey74")
        if visitor.citations:
            yield from console.render(
                Panel(Group(*visitor.citations), title="citation", box=box.SQUARE, border_style=citation_border_style, style=citation_style)
            )

        style = console.get_style("restructuredtext.footer", default="none")
        border_style = console.get_style("restructuredtext.footer_border", default="grey74")
        if visitor.footer:
            yield from console.render(
                Panel(Group(*visitor.footer), title="Footer", box=box.SQUARE, border_style=border_style, style=style)
            )


RST = reST = ReStructuredText = reStructuredText = RestructuredText
