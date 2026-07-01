import argparse
import sys
from typing import Tuple
from rich.panel import Panel
from rich.console import Console
from rich_rst import RestructuredText, __version__
from rich.terminal_theme import TerminalTheme, DEFAULT_TERMINAL_THEME, MONOKAI, NIGHT_OWLISH, DIMMED_MONOKAI
from rich.traceback import install
from rich.text import Text

def rgb(r: int, g: int, b: int) -> Tuple[int, int, int]:
    """
    Function to represent color in RGB format.

    Parameters
    ----------
    r : int
        Red color value.
    g : int
        Green color value.
    b : int
        Blue color value.

    Returns
    -------
    tuple
        A tuple representing the RGB color.
    """
    return (r, g, b)


# Named HTML export themes available via --html-theme
_DRACULA_TERMINAL_THEME = TerminalTheme(
    rgb(40, 42, 54),
    rgb(248, 248, 242),
    [
        rgb(40, 42, 54),
        rgb(255, 85, 85),
        rgb(80, 250, 123),
        rgb(241, 250, 140),
        rgb(189, 147, 249),
        rgb(255, 121, 198),
        rgb(139, 233, 253),
        rgb(255, 255, 255),
    ],
    [
        rgb(40, 42, 54),
        rgb(255, 85, 85),
        rgb(80, 250, 123),
        rgb(241, 250, 140),
        rgb(189, 147, 249),
        rgb(255, 121, 198),
        rgb(139, 233, 253),
        rgb(255, 255, 255),
    ],
)

_HTML_THEMES = {
    "dracula": _DRACULA_TERMINAL_THEME,
    "monokai": MONOKAI,
    "night-owl": NIGHT_OWLISH,
    "dimmed-monokai": DIMMED_MONOKAI,
    "default": DEFAULT_TERMINAL_THEME,
}


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Render reStructuredText to the console with rich-rst")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("path", metavar="PATH", nargs="?", default=None, help="path to file, or - for stdin")
    parser.add_argument("-c", "--force-color", dest="force_color", action="store_true", default=None, help="force color for non-terminals")
    parser.add_argument("-e", "--encoding", dest="encoding", type=str, default="utf-8", help="encoding for file (default: utf-8)")
    parser.add_argument("-w", "--width", type=int, dest="width", default=None, help="width of output (default will auto-detect)")
    parser.add_argument("-hw", "--html-width", type=str, dest="html_width", default="1675px", help="width of html output (default: 1675px)")
    parser.add_argument("-t", "--code-theme", dest="code_theme", type=str, default="monokai", help="pygments code theme")
    parser.add_argument("--show-line-numbers", action="store_true", dest="show_line_numbers", default=False, help="show line numbers for syntax-highlighted code blocks")
    parser.add_argument("-html", "--save-html", type=str, dest="html_filename", default=False, help="save to html")
    parser.add_argument("-r", "--wrap", dest="word_wrap", action="store_true", default=False, help="word wrap long lines")
    parser.add_argument("-s", "--soft-wrap", action="store_true", dest="soft_wrap", default=False, help="enable soft wrapping mode")
    parser.add_argument("-gl", "--guess-lexer", action="store_true", dest="guess_lexer", default=False, help="Whether to guess the lexer for code blocks without specified language")
    parser.add_argument("-dl", "--default-lexer", type=str, dest="default_lexer", default="python", help="The default lexer for code blocks without specified language if no lexer could be guessed or found")
    parser.add_argument("-se", "--show-errors", action="store_true", dest="show_errors", default=False, help="Whether to show errors or not")
    parser.add_argument(
        "--admonition-style",
        dest="admonition_style",
        type=str,
        default="panel",
        choices=["panel", "compact"],
        help="How to render admonitions (default: panel)",
    )
    parser.add_argument(
        "--html-theme",
        dest="html_theme",
        type=str,
        default="dracula",
        choices=list(_HTML_THEMES),
        help="colour theme for --save-html output (default: dracula)",
    )
    parser.add_argument(
        "--list-html-themes",
        action="store_true",
        dest="list_html_themes",
        default=False,
        help="list available HTML export themes and exit",
    )
    parser.add_argument(
        "-o", "--output",
        dest="output",
        type=str,
        default=None,
        help="write rendered plain-text output to FILE instead of stdout",
    )
    args = parser.parse_args()
    # PATH is only optional when --list-html-themes is used.
    if not args.list_html_themes and args.path is None:
        parser.error("the following arguments are required: PATH")
    return args

def main() -> int:
    """The main function."""
    args = parse_arguments()

    if args.list_html_themes:
        for name in sorted(_HTML_THEMES):
            print(name)
        return 0

    # PATH is required at this point (parse_arguments already validated it)

    # NOTE: CSS braces must be doubled ({{ / }}) so that Rich's internal
    # code_format.format(...) call treats them as literal characters.
    # args.html_width is spliced in with a plain str.replace to avoid
    # adding a third round of brace escaping.
    CONSOLE_HTML_FORMAT = """\
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
    {stylesheet}
    body {{
        color: {foreground};
        background-color: {background};
        max-width: HTML_WIDTH_PLACEHOLDER
    }}
    pre {{
        white-space: pre-wrap;       /* Since CSS 2.1 */
        white-space: -moz-pre-wrap;  /* Mozilla, since 1999 */
        white-space: -pre-wrap;      /* Opera 4-6 */
        white-space: -o-pre-wrap;    /* Opera 7 */
        word-wrap: break-word;       /* Internet Explorer 5.5+ */
    }}
    ::-moz-selection {{
      background: #44475a;
    }}
    ::selection {{
      background: #44475a;
    }}
    </style>
    </head>
    <body>
        <pre style="font-family:ui-monospace,'Fira Code',Menlo,'DejaVu Sans Mono',consolas,'Courier New',monospace"><code>{code}</code></pre>
    </body>
    </html>
    """.replace("HTML_WIDTH_PLACEHOLDER", args.html_width)

    record = bool(args.html_filename) or bool(args.output)
    console = Console(force_terminal=args.force_color, width=args.width, record=record)
    if args.path == "-":
        code = sys.stdin.read()
    else:
        try:
            with open(args.path, "rt", encoding=args.encoding) as file_handle:
                code = file_handle.read()
        except OSError as error:
            console.print(
                Panel(
                    Text(
                        f"Could not read {args.path!r}.\n\n"
                        "Check that the file exists and that you have permission to read it.\n"
                        f"{error}",
                    ),
                    title="Input File Error",
                )
            )
            return 1
    rst = RestructuredText(
        code,
        code_theme=args.code_theme,
        show_line_numbers=args.show_line_numbers,
        guess_lexer=args.guess_lexer,
        default_lexer=args.default_lexer,
        show_errors=args.show_errors,
        filename=args.path if args.path != "-" else "<stdin>",
        admonition_style=args.admonition_style,
    )
    if args.output:
        # Render to a file instead of stdout.
        console.print(rst, soft_wrap=args.soft_wrap)
        text_output = console.export_text()
        try:
            with open(args.output, "w", encoding="utf-8") as out_fh:
                out_fh.write(text_output)
        except OSError as error:
            Console().print(
                Panel(
                    Text(f"Could not write to {args.output!r}.\n{error}"),
                    title="Output File Error",
                )
            )
            return 1
    else:
        console.print(rst, soft_wrap=args.soft_wrap)

    if args.html_filename:
        html_theme = _HTML_THEMES.get(args.html_theme, _DRACULA_TERMINAL_THEME)
        console.save_html(args.html_filename, theme=html_theme, code_format=CONSOLE_HTML_FORMAT)
    return 0

if __name__ == "__main__":
    install()
    raise SystemExit(main())
