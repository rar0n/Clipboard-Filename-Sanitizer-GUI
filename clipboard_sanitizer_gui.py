#!/usr/bin/env python3
"""
Clipboard Sanitizer - GUI version (PySide6)

Monitors the clipboard and sanitizes text so it's safe to use as a
Windows/Linux file name. GUI wraps the same logic as the original
CLI tool (clipboard_sanitizer-6-GFL.py), adds a "move parenthesized
text to the end" option, and persists checkbox/settings state to
settings.json next to this script.
"""

import sys
import os
import re
import json
import time
import unicodedata
from datetime import datetime
from typing import Optional, List, Tuple
from html import escape as html_escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QCheckBox, QPushButton, QLabel, QLineEdit,
    QTextEdit, QStatusBar, QSizePolicy, QToolButton
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(SCRIPT_DIR, "settings.json")

# Log colors
LOG_BG_COLOR = "#0a0a0a"          # almost black
LOG_INFO_COLOR = "#f2f2f2"        # almost white - timestamps, start/stop banners
LOG_CHANGED_COLOR = "#ff9d33"     # orange - clipboard text that was modified
LOG_UNCHANGED_COLOR = "#b3b3b3"   # light gray - clipboard text left as-is
LOG_IGNORED_COLOR = "#ff6b6b"     # light red - clipboard text skipped (URL/path/hash ignore)

# Button colors
COLOR_DARK_BLUE = "#3a4864"
COLOR_DARK_GREEN = "#3f5442"
COLOR_DARK_RED = "#5c3a3a"
COLOR_DARK_PURPLE = "#4a3f5e"


def button_style(bg_color: str) -> str:
    """Stylesheet for a dark-colored push button with light text."""
    return (
        f"QPushButton {{ background-color: {bg_color}; color: #f2f2f2; "
        f"border: 1px solid #222222; border-radius: 4px; padding: 4px 12px; }}"
        f"QPushButton:hover {{ border: 1px solid #555555; }}"
        f"QPushButton:pressed {{ background-color: #222222; }}"
    )


# ---------------------------------------------------------------------------
# Bracket handling (new "move parenthesized text to end" feature)
# ---------------------------------------------------------------------------

# Opening -> closing bracket pairs. Includes ASCII plus common CJK / other
# "parenthesis-like" bracket characters.
BRACKET_PAIRS = {
    '(': ')',
    '[': ']',
    '{': '}',
    '（': '）',  # fullwidth parenthesis
    '【': '】',  # black lenticular bracket
    '「': '」',  # corner bracket
    '『': '』',  # white corner bracket
    '〈': '〉',  # angle bracket
    '《': '》',  # double angle bracket
    '〔': '〕',  # tortoise shell bracket
    '〖': '〗',  # white lenticular bracket
    '〘': '〙',  # white tortoise shell bracket
    '〚': '〛',  # white square bracket
    '‹': '›',   # single guillemet
    '«': '»',   # double guillemet
}
OPENERS = set(BRACKET_PAIRS.keys())
CLOSERS = {v: k for k, v in BRACKET_PAIRS.items()}


def _parse_bracket_group(text: str, start: int) -> Optional[int]:
    """
    text[start] must be an opening bracket. Walk forward, handling nesting
    of same/different bracket types, and return the index just past the
    matching closing bracket. Returns None if the group is never closed.
    """
    stack: List[str] = [text[start]]
    i = start + 1
    n = len(text)
    while i < n and stack:
        ch = text[i]
        if ch in OPENERS:
            stack.append(ch)
        elif ch in CLOSERS and CLOSERS[ch] == stack[-1]:
            stack.pop()
        i += 1
    return None if stack else i


def move_parenthesized_to_end(text: str) -> str:
    """
    Move bracketed group(s) - normal, square, curly, or common non-Latin
    bracket styles - to the end of the string, but ONLY if they sit at the
    very beginning of the text (a single leading group, or a run of several
    leading groups back-to-back). Parenthesized text anywhere else in the
    string is left exactly as-is.

    If the string consists of ONLY bracketed content (nothing meaningful
    outside of it), the text is left untouched.
    """
    n = len(text)
    i = 0
    groups: List[str] = []

    while i < n:
        if text[i] in OPENERS:
            end = _parse_bracket_group(text, i)
            if end is None:
                # Unclosed - treat as ordinary text, stop looking for more.
                break
            groups.append(text[i:end])
            i = end
            continue
        elif text[i].isspace() and groups:
            # Only keep scanning past whitespace if it's followed by
            # another leading group; otherwise this is where the
            # "meaningful" remainder starts.
            j = i
            while j < n and text[j].isspace():
                j += 1
            if j < n and text[j] in OPENERS:
                i = j
                continue
            break
        else:
            break

    if not groups:
        return text

    remainder = text[i:]
    if not remainder.strip():
        # Only text inside parenthesis (single or several groups) -> do nothing.
        return text

    cleaned_remainder = re.sub(r'\s+', ' ', remainder).strip()
    parens_part = ' '.join(g.strip() for g in groups)
    return f"{cleaned_remainder} {parens_part}".strip()


# ---------------------------------------------------------------------------
# Ported logic from the CLI tool
# ---------------------------------------------------------------------------

def is_url(text: str) -> bool:
    """Check if the text looks like a URL."""
    return text.startswith(('http://', 'https://'))


def is_file_path(text: str) -> bool:
    """Check if the text looks like an absolute file path."""
    return os.path.isabs(text)


HASH_HEX_RE = re.compile(r'\A[0-9a-fA-F]{32}\Z|\A[0-9a-fA-F]{64}\Z')


def is_hash(text: str) -> bool:
    """Check if the text is (only) an MD5 (32 hex chars) or SHA256 (64 hex
    chars) checksum, ignoring surrounding whitespace."""
    stripped = text.strip()
    return bool(HASH_HEX_RE.match(stripped))


def first_line(text: str) -> str:
    """Return the first line of text, with leading newlines/CR stripped."""
    if not text:
        return ""
    result = text.lstrip('\n\r')
    return result.split('\n')[0].split('\r')[0]


def get_clipboard_type(clipboard) -> Optional[str]:
    """
    Determine the type of content currently in the clipboard using Qt's own
    QClipboard, via its mimeData() - no external processes involved, so
    there's no risk of the classic "app owns the X11 selection and shells
    out to xclip to read it back" deadlock. Returns None if the clipboard
    is empty, 'text' if it has a text representation, 'non-text' otherwise
    (e.g. an image or file copied from a file manager with no text form).
    """
    mime = clipboard.mimeData()
    if mime.hasText() and mime.text():
        return 'text'
    if mime.hasImage() or mime.hasUrls() or mime.formats():
        return 'non-text'
    return None


def remove_trailing_symbols(text: str) -> str:
    """Remove trailing symbols that aren't alphanumeric or part of any language."""
    def is_valid_char(char):
        category = unicodedata.category(char)
        if category.startswith(('L', 'N', 'M')) or category.startswith('Z'):
            return True
        # Don't strip a closing bracket that "move parenthesized text to
        # end" may have deliberately placed at the very end of the string.
        if char in CLOSERS or char in OPENERS:
            return True
        return False

    # Strip whitespace and invalid symbols together, in one loop. Stopping at
    # the first whitespace char left leftovers like "Title - |" -> "Title -"
    # (the space shielded the "-"), which only disappeared on a second pass.
    result = text
    while result and (result[-1].isspace() or not is_valid_char(result[-1])):
        result = result[:-1]
    return result


def remove_emoji(text: str) -> str:
    """Remove emoji characters from text."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0000257F"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "\U0000FE00-\U0000FE0F"
        "\U0001F1E0-\U0001F1FF"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)


def sanitize_filename(text: str) -> str:
    """Sanitize a string to be a valid filename. Does NOT strip to a single
    line - that's handled separately (and optionally) by the caller."""
    result = text

    basic_replacements = {
        '<': '(',
        '>': ')',
        ':': ';',
        '"': "_",
        '”': '_',
        '“': '_',
        '/': '-',
        '\\': '-',
        '|': '-',
        '?': '_',
        '*': '+',
    }
    for old, new in basic_replacements.items():
        result = result.replace(old, new)

    reserved_names = {
        r'\bCON\b': 'CON_',
        r'\bPRN\b': 'PRN_',
        r'\bAUX\b': 'AUX_',
        r'\bNUL\b': 'NUL_',
        r'\bCOM([1-9])\b': r'COM\1_',
        r'\bLPT([1-9])\b': r'LPT\1_'
    }
    for pattern, replacement in reserved_names.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    result = result.rstrip('. ')
    result = result.lstrip()
    return result


def is_latin_letter(char: str) -> bool:
    return 'a' <= char.lower() <= 'z'


# A "number token" is a digit run that may contain internal connecting
# punctuation, so dates/decimals like "3.04" or "2-15-26" are treated as one
# unit rather than three separate pieces.
NUMBER_TOKEN_RE = re.compile(r'\d+(?:[.\-/:,]\d+)*')


def _classify_by_nearest_letter(text: str, start: int, end: int, default: str = 'latin') -> str:
    """
    For a non-letter span (a number token, or a lone symbol), find the
    nearest actual letter - skipping whitespace, digits, and other symbols -
    checking forward from `end` first, then backward from `start`. Returns
    'latin' or 'other' based on that letter, or `default` if no letter is
    found anywhere in the string.
    """
    n = len(text)

    i = end
    while i < n and not text[i].isalpha():
        i += 1
    if i < n:
        return 'latin' if is_latin_letter(text[i]) else 'other'

    j = start - 1
    while j >= 0 and not text[j].isalpha():
        j -= 1
    if j >= 0:
        return 'latin' if is_latin_letter(text[j]) else 'other'

    return default


def _build_latin_flags(text: str, attach_symbols: bool = True) -> List[bool]:
    """
    Classify every character in `text` as "Latin-side" (True) or
    "non-Latin-side" (False) for the purpose of apply_latin_first.

    - Letters: Latin letters are True, other-script letters are False.
    - Numbers (including punctuated dates/decimals as one token): the whole
      token takes on the type of whichever letter is nearest to it, ignoring
      whitespace, digits, and other symbols in between.
    - Symbols (anything else, e.g. underscores left over from filename
      sanitizing): same "nearest letter" treatment if attach_symbols is True,
      otherwise always False (the old behavior - never counted as Latin).
    - Whitespace: always False.
    """
    n = len(text)
    flags = [False] * n
    i = 0
    while i < n:
        ch = text[i]
        if ch.isalpha():
            flags[i] = is_latin_letter(ch)
            i += 1
        elif ch.isdigit():
            match = NUMBER_TOKEN_RE.match(text, i)
            span_end = match.end() if match else i + 1
            attach = _classify_by_nearest_letter(text, i, span_end)
            for k in range(i, span_end):
                flags[k] = (attach == 'latin')
            i = span_end
        elif ch.isspace():
            i += 1
        else:
            if attach_symbols:
                attach = _classify_by_nearest_letter(text, i, i + 1)
                flags[i] = (attach == 'latin')
            i += 1
    return flags


def apply_latin_first(text: str, separator: Optional[str] = None, attach_symbols: bool = True) -> str:
    """Move non-Latin characters (and their attached numbers/symbols) from
    the beginning to the end of the string."""
    if not text:
        return text

    flags = _build_latin_flags(text, attach_symbols=attach_symbols)

    if not any(flags):
        return text

    first_latin_index = flags.index(True)

    if first_latin_index <= 0:
        # No prefix to move or starts with Latin letter/number
        return text

    # Split the string
    prefix = text[:first_latin_index]
    remainder = text[first_latin_index:]

    # Join with separator if provided
    if separator is not None:
        result = remainder + separator + prefix
    else:
        result = remainder + prefix

    # Ensure no trailing whitespace
    return result.rstrip()


def capitalize_words(text: str) -> str:
    """Capitalize the first letter of every run of letters, lowercasing the
    rest of that run. Unicode-aware; digits/underscores/punctuation are not
    treated as letters and don't break words apart from each other, but a
    letter run adjacent to an apostrophe (e.g. "don't") is still split into
    two separately-capitalized runs, since apostrophes aren't letters."""
    def cap(m):
        word = m.group(0)
        return word[0].upper() + word[1:].lower()
    return re.sub(r"[^\W\d_]+", cap, text)


def get_timestamp() -> str:
    return datetime.now().strftime("%H:%M")


def get_timestamp_detailed() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Options + settings persistence
# ---------------------------------------------------------------------------

class SanitizerOptions:
    """Mutable bag of the current checkbox/field states. Read fresh each
    clipboard poll, so toggling checkboxes takes effect immediately."""

    def __init__(self):
        self.strip_to_one_line = True
        self.remove_emoji = False
        self.latin_first = False
        self.attach_symbols = True
        self.remove_trailing_symbols = False
        self.move_parens = False
        self.keep_quote_symbol = False
        self.timestamp = False
        self.separator = '-'
        self.use_separator = False
        self.ignore_urls = True
        self.ignore_file_paths = True
        self.ignore_hashes = False
        self.case_mode = 'none'  # 'none' | 'lower' | 'upper' | 'title'

    def to_dict(self) -> dict:
        return {
            'strip_to_one_line': self.strip_to_one_line,
            'remove_emoji': self.remove_emoji,
            'latin_first': self.latin_first,
            'attach_symbols': self.attach_symbols,
            'remove_trailing_symbols': self.remove_trailing_symbols,
            'move_parens': self.move_parens,
            'keep_quote_symbol': self.keep_quote_symbol,
            'timestamp': self.timestamp,
            'separator': self.separator,
            'use_separator': self.use_separator,
            'ignore_urls': self.ignore_urls,
            'ignore_file_paths': self.ignore_file_paths,
            'ignore_hashes': self.ignore_hashes,
            'case_mode': self.case_mode,
        }

    def load_dict(self, data: dict):
        self.strip_to_one_line = data.get('strip_to_one_line', True)
        self.remove_emoji = data.get('remove_emoji', False)
        self.latin_first = data.get('latin_first', False)
        self.attach_symbols = data.get('attach_symbols', True)
        self.remove_trailing_symbols = data.get('remove_trailing_symbols', False)
        self.move_parens = data.get('move_parens', False)
        self.keep_quote_symbol = data.get('keep_quote_symbol', False)
        self.timestamp = data.get('timestamp', False)
        self.separator = data.get('separator', '-')
        self.use_separator = data.get('use_separator', False)
        self.ignore_urls = data.get('ignore_urls', True)
        self.ignore_file_paths = data.get('ignore_file_paths', True)
        self.ignore_hashes = data.get('ignore_hashes', False)
        case_mode = data.get('case_mode', 'none')
        self.case_mode = case_mode if case_mode in ('none', 'lower', 'upper', 'title') else 'none'


def save_settings(options: SanitizerOptions):
    with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
        json.dump(options.to_dict(), f, indent=2, ensure_ascii=False)


def load_settings(options: SanitizerOptions):
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                options.load_dict(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Sanitize pipeline
# ---------------------------------------------------------------------------

def sanitize(text: str, opts: SanitizerOptions) -> str:
    result = text

    if opts.strip_to_one_line:
        result = first_line(result)

    if opts.remove_emoji:
        result = remove_emoji(result)

    result = sanitize_filename(result)

    # If the text started with a quotation mark (already turned into "_" by
    # sanitize_filename's basic_replacements), optionally unhook that "_"
    # from the rest of the pipeline so later steps (move-parens-to-end,
    # non-Latin-first) can't drag it away from the very start.
    pinned_quote_prefix = ''
    if opts.keep_quote_symbol and result.startswith('_'):
        pinned_quote_prefix = '_'
        result = result[1:]

    if opts.move_parens:
        result = move_parenthesized_to_end(result)

    if opts.latin_first:
        separator = opts.separator if opts.use_separator else None
        result = apply_latin_first(result, separator, opts.attach_symbols)

    if opts.remove_trailing_symbols:
        result = remove_trailing_symbols(result)

    if pinned_quote_prefix:
        result = pinned_quote_prefix + result.lstrip()

    if opts.case_mode == 'lower':
        result = result.lower()
    elif opts.case_mode == 'upper':
        result = result.upper()
    elif opts.case_mode == 'title':
        result = capitalize_words(result)

    return result.rstrip()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    POLL_INTERVAL_MS = 100

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clipboard Filename Sanitizer GUI 2026.07.26 (raron)")
        self.resize(640, 700)

        self.options = SanitizerOptions()
        load_settings(self.options)

        self.clipboard = QApplication.clipboard()
        self.last_text = ""
        self.monitoring = False
        self._height_before_collapse = 0

        self._build_ui()
        self._apply_options_to_widgets()

        # Start with the Options box collapsed. Set the state directly (no
        # signal) so the toggle handler's resize logic doesn't run before the
        # window has been laid out; expanding later restores the full height.
        self._height_before_collapse = self.height()
        self.btn_options_toggle.blockSignals(True)
        self.btn_options_toggle.setChecked(False)
        self.btn_options_toggle.blockSignals(False)
        self.btn_options_toggle.setArrowType(Qt.RightArrow)
        self.options_box.setVisible(False)
        self.resize(self.width(), 480)

        self.timer = QTimer(self)
        self.timer.setInterval(self.POLL_INTERVAL_MS)
        self.timer.timeout.connect(self._poll_clipboard)

        # Begin monitoring right away; the button still stops/starts it.
        self._toggle_monitoring()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)

        # Collapsible header: clicking it hides/shows the whole options box.
        self.btn_options_toggle = QToolButton()
        self.btn_options_toggle.setText("Options")
        self.btn_options_toggle.setCheckable(True)
        self.btn_options_toggle.setChecked(True)
        self.btn_options_toggle.setArrowType(Qt.DownArrow)
        self.btn_options_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_options_toggle.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 2px 0px; }"
        )
        self.btn_options_toggle.setToolTip("Show / hide the options.")
        self.btn_options_toggle.toggled.connect(self._on_options_toggled)
        layout.addWidget(self.btn_options_toggle, 0, Qt.AlignLeft)

        options_box = QGroupBox()
        self.options_box = options_box
        options_outer = QVBoxLayout(options_box)
        columns_row = QHBoxLayout()
        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        columns_row.addLayout(col1)
        columns_row.addLayout(col2)
        options_outer.addLayout(columns_row)

        # -- Column 1: text-transform options --
        self.cb_strip_one_line = QCheckBox("Strip to one line")
        self.cb_strip_one_line.setToolTip(
            "Keep only the first line of\nthe clipboard text (current\ndefault). Turn off to let\nmulti-line clipboard text pass\nthrough as-is."
        )

        self.cb_remove_emoji = QCheckBox("Remove emoji")
        self.cb_remove_emoji.setToolTip("Strip emoji characters\nfrom the clipboard text.")

        self.cb_latin_first = QCheckBox("Non-Latin to end")
        self.cb_latin_first.setToolTip(
            "Move any non-Latin-script\ncharacters (and attached\n"
            "numbers/symbols) from the\nstart of the text to the end."
        )

        self.cb_attach_symbols = QCheckBox("Attach symbols to text")
        self.cb_attach_symbols.setToolTip(
            "When moving non-Latin text,\nkeep neighboring symbols\n"
            "(underscores, quotes, etc.)\nattached to whichever side\n"
            "(Latin/non-Latin) they're\nnext to, instead of always\n"
            "treating them as Latin-side."
        )

        self.cb_remove_trailing_symbols = QCheckBox("Remove trailing symbols")
        self.cb_remove_trailing_symbols.setToolTip(
            "Strip trailing characters that\naren't letters, numbers, or\n"
            "brackets (e.g. -, |, =, +)."
        )

        self.cb_move_parens = QCheckBox("Move leading (...) to end")
        self.cb_move_parens.setToolTip(
            "Move a (parenthesized) group\nto the end, but only if it\n"
            "sits at the very start of the\ntext. Parens elsewhere in the\n"
            "text are left as-is. If the\nwhole text is nothing but\n"
            "parenthesized groups, it's\nleft untouched too."
        )

        self.cb_keep_quote_symbol = QCheckBox("Pin quote symbol in place")
        self.cb_keep_quote_symbol.setToolTip(
            "If the text starts with a\nquotation mark (converted to\n"
            "\"_\"), keep that \"_\" pinned at\nthe very start even if other\n"
            "options above would otherwise\nmove it away from there."
        )

        for cb in (self.cb_strip_one_line, self.cb_remove_emoji, self.cb_latin_first, self.cb_attach_symbols,
                   self.cb_remove_trailing_symbols, self.cb_move_parens, self.cb_keep_quote_symbol):
            col1.addWidget(cb)
        col1.addStretch()

        # -- Column 2: ignore / logging options --
        self.cb_timestamp = QCheckBox("Show timestamps")
        self.cb_timestamp.setToolTip("Prefix each log line with\nthe current time (HH:MM).")

        self.cb_ignore_urls = QCheckBox("Ignore URLs")
        self.cb_ignore_urls.setToolTip(
            "Skip sanitizing (and don't\ncopy back) clipboard text\n"
            "that looks like a URL\n(starts with http:// or https://)."
        )

        self.cb_ignore_file_paths = QCheckBox("Ignore file paths")
        self.cb_ignore_file_paths.setToolTip(
            "Skip sanitizing (and don't\ncopy back) clipboard text\n"
            "that looks like an absolute\nfile path."
        )

        self.cb_ignore_hashes = QCheckBox("Ignore checksums")
        self.cb_ignore_hashes.setToolTip(
            "Skip sanitizing clipboard text\nthat is just an MD5 (32 hex\n"
            "chars) or SHA256 (64 hex\nchars) checksum."
        )

        self.case_group = QGroupBox("Case (pick one or None)")
        case_layout = QVBoxLayout(self.case_group)

        self.cb_lowercase = QCheckBox("Lowercase")
        self.cb_lowercase.setToolTip("Convert the whole text to\nlowercase.")

        self.cb_uppercase = QCheckBox("CAPITALIZE")
        self.cb_uppercase.setToolTip("Convert the whole text to\nUPPERCASE.")

        self.cb_titlecase = QCheckBox("Capitalize Each Word")
        self.cb_titlecase.setToolTip(
            "Capitalize The First Letter\nOf Each Word, lowercasing the\n"
            "rest. Note: a word right next\nto an apostrophe (don't) is\n"
            "still split and capitalized\non both sides (Don'T)."
        )

        for cb in (self.cb_lowercase, self.cb_uppercase, self.cb_titlecase):
            case_layout.addWidget(cb)

        for cb in (self.cb_timestamp, self.cb_ignore_urls,
                   self.cb_ignore_file_paths, self.cb_ignore_hashes):
            col2.addWidget(cb)
        col2.addWidget(self.case_group)
        col2.addStretch()

        sep_row = QHBoxLayout()
        self.cb_use_separator = QCheckBox("Use separator when moving non-Latin prefix:")
        self.cb_use_separator.setToolTip(
            "Insert this separator between\nthe moved non-Latin prefix\nand the rest of the text."
        )
        self.le_separator = QLineEdit()
        self.le_separator.setMaxLength(5)
        self.le_separator.setFixedWidth(60)
        self.le_separator.setToolTip(
            "Applied when you finish editing\n(press Enter or click away),\nnot on every keystroke."
        )
        sep_row.addWidget(self.cb_use_separator)
        sep_row.addWidget(self.le_separator)
        sep_row.addStretch()
        options_outer.addLayout(sep_row)

        layout.addWidget(options_box)

        for cb in (self.cb_strip_one_line, self.cb_remove_emoji, self.cb_latin_first, self.cb_attach_symbols,
                   self.cb_remove_trailing_symbols, self.cb_move_parens, self.cb_keep_quote_symbol,
                   self.cb_timestamp, self.cb_ignore_urls, self.cb_ignore_file_paths,
                   self.cb_ignore_hashes, self.cb_use_separator):
            cb.stateChanged.connect(self._on_option_changed)
        # Re-filtering on every keystroke would be noisy, so the separator
        # field only triggers a re-run when editing is finished (focus-out
        # or Enter) - editingFinished covers both.
        self.le_separator.editingFinished.connect(self._on_option_changed)

        # The three case-conversion options are mutually exclusive, so they
        # go through a dedicated handler that unchecks the other two first.
        for cb in (self.cb_lowercase, self.cb_uppercase, self.cb_titlecase):
            cb.stateChanged.connect(lambda _state, box=cb: self._on_case_option_toggled(box))

        # -- Buttons --
        button_row = QHBoxLayout()
        self.btn_toggle = QPushButton("Start Monitoring")
        self.btn_toggle.setStyleSheet(button_style(COLOR_DARK_BLUE))
        self.btn_toggle.clicked.connect(self._toggle_monitoring)
        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.setStyleSheet(button_style(COLOR_DARK_GREEN))
        self.btn_save_settings.clicked.connect(self._on_save_settings)
        self.btn_clear_log = QPushButton("Clear Log")
        self.btn_clear_log.setStyleSheet(button_style(COLOR_DARK_RED))
        self.btn_clear_log.clicked.connect(lambda: self.log.clear())
        button_row.addWidget(self.btn_toggle)
        button_row.addWidget(self.btn_save_settings)
        button_row.addWidget(self.btn_clear_log)
        layout.addLayout(button_row)

        # -- Output log / last result --
        layout.addWidget(QLabel("Output (most recent sanitized clipboard text at the bottom):"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log.setStyleSheet(
            f"QTextEdit {{ background-color: {LOG_BG_COLOR}; "
            f"color: {LOG_INFO_COLOR}; border: none; }}"
        )
        layout.addWidget(self.log)

        self.setCentralWidget(central)

        self.status = QStatusBar()
        self.status.showMessage("Idle - press \"Start Monitoring\" to begin")
        self.setStatusBar(self.status)

    def _apply_options_to_widgets(self):
        """Set widget states from self.options. Signals are blocked while
        doing this - otherwise each setChecked() call fires
        _on_option_changed(), which reads ALL current widget states
        (including ones further down this list that haven't been set yet,
        still showing their unchecked default) and overwrites
        self.options with those not-yet-applied values."""
        o = self.options
        checkbox_values = (
            (self.cb_strip_one_line, o.strip_to_one_line),
            (self.cb_remove_emoji, o.remove_emoji),
            (self.cb_latin_first, o.latin_first),
            (self.cb_attach_symbols, o.attach_symbols),
            (self.cb_remove_trailing_symbols, o.remove_trailing_symbols),
            (self.cb_move_parens, o.move_parens),
            (self.cb_keep_quote_symbol, o.keep_quote_symbol),
            (self.cb_timestamp, o.timestamp),
            (self.cb_ignore_urls, o.ignore_urls),
            (self.cb_ignore_file_paths, o.ignore_file_paths),
            (self.cb_ignore_hashes, o.ignore_hashes),
            (self.cb_use_separator, o.use_separator),
        )
        for checkbox, value in checkbox_values:
            checkbox.blockSignals(True)
            checkbox.setChecked(value)
            checkbox.blockSignals(False)

        self.le_separator.blockSignals(True)
        self.le_separator.setText(o.separator)
        self.le_separator.blockSignals(False)

        case_checkboxes = (
            (self.cb_lowercase, 'lower'),
            (self.cb_uppercase, 'upper'),
            (self.cb_titlecase, 'title'),
        )
        for checkbox, mode in case_checkboxes:
            checkbox.blockSignals(True)
            checkbox.setChecked(o.case_mode == mode)
            checkbox.blockSignals(False)

    # -- Option change handlers ---------------------------------------------

    def _on_option_changed(self, *_args):
        o = self.options
        o.strip_to_one_line = self.cb_strip_one_line.isChecked()
        o.remove_emoji = self.cb_remove_emoji.isChecked()
        o.latin_first = self.cb_latin_first.isChecked()
        o.attach_symbols = self.cb_attach_symbols.isChecked()
        o.remove_trailing_symbols = self.cb_remove_trailing_symbols.isChecked()
        o.move_parens = self.cb_move_parens.isChecked()
        o.keep_quote_symbol = self.cb_keep_quote_symbol.isChecked()
        o.timestamp = self.cb_timestamp.isChecked()
        o.ignore_urls = self.cb_ignore_urls.isChecked()
        o.ignore_file_paths = self.cb_ignore_file_paths.isChecked()
        o.ignore_hashes = self.cb_ignore_hashes.isChecked()
        o.use_separator = self.cb_use_separator.isChecked()
        o.separator = self.le_separator.text()

        if self.cb_lowercase.isChecked():
            o.case_mode = 'lower'
        elif self.cb_uppercase.isChecked():
            o.case_mode = 'upper'
        elif self.cb_titlecase.isChecked():
            o.case_mode = 'title'
        else:
            o.case_mode = 'none'

        self._reprocess_current_clipboard()

    def _on_case_option_toggled(self, box: QCheckBox):
        """The three case-conversion checkboxes act like a radio group:
        checking one unchecks the other two (unchecking the active one
        just clears it, going back to 'no case conversion')."""
        if box.isChecked():
            for other in (self.cb_lowercase, self.cb_uppercase, self.cb_titlecase):
                if other is not box:
                    other.blockSignals(True)
                    other.setChecked(False)
                    other.blockSignals(False)
        self._on_option_changed()

    def _on_options_toggled(self, expanded: bool):
        """Collapse/expand the options box. The window height follows, so the
        log doesn't just stretch into the freed space; expanding restores the
        height the window had before it was collapsed."""
        if expanded:
            self.btn_options_toggle.setArrowType(Qt.DownArrow)
            self.options_box.setVisible(True)
            if self._height_before_collapse and not self.isMaximized():
                self.resize(self.width(), self._height_before_collapse)
        else:
            self._height_before_collapse = self.height()
            freed = (self.options_box.height()
                     + self.centralWidget().layout().spacing())
            self.btn_options_toggle.setArrowType(Qt.RightArrow)
            self.options_box.setVisible(False)
            if not self.isMaximized():
                self.resize(self.width(), max(self.minimumHeight(),
                                              self.height() - freed))

    def _on_save_settings(self):
        save_settings(self.options)
        self.status.showMessage("Settings saved.", 3000)

    # -- Monitoring ----------------------------------------------------------

    def _log_banner(self, label: str):
        """Write a dashed banner line into the log, with a blank line
        before and after it, for visibility."""
        self.log.append("")
        self.log.append(f'<span style="color:{LOG_INFO_COLOR};">'
                         f'---------- {html_escape(label)} ----------</span>')
        self.log.append("")

    def _log_clip(self, text: str, changed: bool):
        """Log a captured clipboard entry. Orange if it was modified by the
        sanitizer, light gray if it was left unchanged."""
        color = LOG_CHANGED_COLOR if changed else LOG_UNCHANGED_COLOR
        body = f'<span style="color:{color};">{html_escape(text)}</span>'
        if self.options.timestamp:
            ts = f'<span style="color:{LOG_INFO_COLOR};">{get_timestamp()}:</span> '
            self.log.append(ts + body)
        else:
            self.log.append(body)

    def _log_ignored(self, text: str):
        """Log a clipboard entry that was skipped entirely because it
        matched an active ignore option (URL/file path/checksum), in
        light red."""
        body = f'<span style="color:{LOG_IGNORED_COLOR};">{html_escape(text)}</span>'
        if self.options.timestamp:
            ts = f'<span style="color:{LOG_INFO_COLOR};">{get_timestamp()}:</span> '
            self.log.append(ts + body)
        else:
            self.log.append(body)

    def _should_ignore(self, text: str) -> bool:
        return (
            (self.options.ignore_urls and is_url(text)) or
            (self.options.ignore_file_paths and is_file_path(text)) or
            (self.options.ignore_hashes and is_hash(text))
        )

    def _reprocess_current_clipboard(self):
        """Whenever an option changes, re-run whatever is currently on the
        clipboard through the sanitizer with the updated settings, log the
        result, and copy it back to the clipboard - so the clipboard always
        reflects the latest log entry (unless the text is ignored, in which
        case it's left untouched, same as during normal monitoring)."""
        current_text = self.clipboard.text()
        if not current_text:
            return

        content_type = get_clipboard_type(self.clipboard)
        if content_type != 'text':
            return

        marker = f'<span style="color:{LOG_INFO_COLOR};">&#8635; </span>'

        if self._should_ignore(current_text):
            body = f'<span style="color:{LOG_IGNORED_COLOR};">{html_escape(current_text)}</span>'
            self.log.append(marker + body)
            self.last_text = current_text
            return

        sanitized = sanitize(current_text, self.options)
        changed = sanitized != current_text

        if changed:
            try:
                self.clipboard.setText(sanitized)
            except Exception as e:
                self.status.showMessage(f"Clipboard write error: {e}", 3000)

        color = LOG_CHANGED_COLOR if changed else LOG_UNCHANGED_COLOR
        body = f'<span style="color:{color};">{html_escape(sanitized)}</span>'
        self.log.append(marker + body)
        self.last_text = sanitized

    def _toggle_monitoring(self):
        if self.monitoring:
            self.timer.stop()
            self.monitoring = False
            self.btn_toggle.setText("Start Monitoring")
            self.btn_toggle.setStyleSheet(button_style(COLOR_DARK_BLUE))
            stop_time = get_timestamp_detailed()
            self._log_banner(f"Stopped at {stop_time}")
            self.status.showMessage(f"Stopped at {stop_time}")
        else:
            # Empty last_text means whatever is already on the clipboard
            # counts as new: the first poll sanitizes (or ignores/logs) it,
            # so there's no need to copy something else and re-copy it.
            self.last_text = ""
            self.timer.start()
            self.monitoring = True
            self.btn_toggle.setText("Stop Monitoring")
            self.btn_toggle.setStyleSheet(button_style(COLOR_DARK_PURPLE))
            start_time = get_timestamp_detailed()
            self._log_banner(f"Started at {start_time}")
            self.status.showMessage(f"Monitoring since {start_time}")

    def _poll_clipboard(self):
        current_text = self.clipboard.text()

        if current_text == self.last_text:
            return

        content_type = get_clipboard_type(self.clipboard)
        if content_type == 'text' and self._should_ignore(current_text):
            self._log_ignored(current_text)
            self.last_text = current_text
        elif content_type == 'text':
            sanitized = sanitize(current_text, self.options)
            changed = sanitized != current_text

            if changed:
                try:
                    self.clipboard.setText(sanitized)
                except Exception as e:
                    self.status.showMessage(f"Clipboard write error: {e}", 3000)

            self._log_clip(sanitized, changed)
            self.last_text = sanitized
        else:
            self.last_text = current_text

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
