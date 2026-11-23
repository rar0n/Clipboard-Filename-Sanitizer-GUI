# Clipboard Filename Sanitizer GUI - Turn copied text into a safe one-line file name

- Watches the clipboard and rewrites copied text so it can be used as a file
  name on Linux, Windows and macOS (one line, no forbidden characters).
- Copy a title, a headline or a filename from anywhere, paste it as a file name.
  No extra steps in between.

<img width="640" height="728" alt="image" src="https://github.com/user-attachments/assets/2e523057-21aa-4e3b-8fd3-1fdf7e377c3c" />


### Features

Basically

  - **Monitors the clipboard** (starts automatically) and replaces the
    clipboard text with a sanitized, one-line version.
  - **Log of everything it sees**, color coded:
    - Orange: text that was changed
    - Light gray: text that was already fine
    - Light red: text that was skipped (URL, file path or checksum)

What gets sanitized:
  - Characters that are illegal on Windows (and awkward elsewhere) are replaced:

    | Original | Becomes |
    |---|---|
    | `<` `>` | `(` `)` |
    | `:` | `;` |
    | `"` `“` `”` | `_` |
    | `/` `\` `\|` | `-` |
    | `?` | `_` |
    | `*` | `+` |

  - Windows reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`,
    `LPT1`-`LPT9`) get an underscore appended.
  - Trailing dots and spaces, and leading spaces, are removed.

Optional extras (all individually switchable, see Options below):
  - Strip to one line (on by default)
  - Remove emoji
  - Move leading non-Latin text (Japanese titles etc.) to the end, with an
    optional separator
  - Move a leading `(...)` / `[...]` / `{...}` group to the end
  - Remove trailing symbols
  - Lowercase, UPPERCASE or Capitalize Each Word
  - Ignore URLs, absolute file paths and MD5 / SHA256 checksums
  - Optional timestamps in the log

Changing any option immediately re-runs the text currently on the clipboard
through the sanitizer, so you can see the effect right away.


### Vibe coded

Yes. Full disclosure: this is mostly written by Claude (Anthropic), from my
descriptions of what I wanted and what I observed when I tried it.
Experiment with the options!

    2026 Ragnar Aronsen (raron) ( But mostly Claude :) )


## Install

Requires Python 3.10 or newer. The only dependency is
[PySide6](https://pypi.org/project/PySide6/) (the Qt bindings).

Developed and used on Linux Mint. The Windows and macOS instructions below
are the standard ones, but I haven't tested them myself.

### Getting the program

Either download the repository as a ZIP file from the GitHub page
(green **Code** button, then **Download ZIP**) and extract it into a folder,
or use `git` to clone it into a local folder:

```bash
git clone https://github.com/rar0n/Clipboard-Filename-Sanitizer-GUI.git
cd Clipboard-Filename-Sanitizer-GUI
```

With a clone, `git pull` later fetches updates.

### Linux

1. Get the program into a folder (see above). `cd` to that folder or just
   right-click the folder and select "Open in Terminal".
2. Install dependencies into a venv (virtual environment):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   (If `python3 -m venv` complains about `ensurepip`, you may need
   `sudo apt install python3-venv`.)

### Windows

1. Install [Python](https://www.python.org/downloads/windows/) if you haven't.
   In the installer, tick **"Add python.exe to PATH"**.
2. Get the program into a folder (see above). In File Explorer, open the folder,
   type `cmd` (or `powershell`) in the address bar and press Enter, to open a
   terminal there.
3. Create the venv and install dependencies. The venv is created the same way
   in both shells, only activating it differs:

   **Command Prompt:**
   ```bat
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

   **PowerShell:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   (If PowerShell refuses to run the activate script with an error about
   execution policies, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
   once, or just use Command Prompt.)

   If `python` isn't found, try `py -m venv venv` instead.

(The venv prompt shows `(venv)` when it's active. Activate it again in each new terminal.)

### macOS

Same as Linux (`python3 -m venv venv`, `source venv/bin/activate`,
`pip install -r requirements.txt`).


## Usage

1. Run the program from its folder, in a terminal. Activate the venv first.

    Linux / macOS:
    ```bash
    source venv/bin/activate
    python3 clipboard_sanitizer_gui.py
    ```
    Windows (Command Prompt):
    ```bat
    venv\Scripts\activate
    python clipboard_sanitizer_gui.py
    ```
    Windows (PowerShell):
    ```powershell
    .\venv\Scripts\Activate.ps1
    python clipboard_sanitizer_gui.py
    ```
2. Monitoring starts right away. Whatever is already on the clipboard is
   sanitized as well. Copy some text, and the clipboard now holds the
   sanitized version, ready to paste as a file name.
3. Use **Stop Monitoring** / **Start Monitoring** to pause and resume.
   Starting also sanitizes the text currently on the clipboard.
4. Click **Options** to show or hide the option checkboxes (hidden at start).


### Linux launcher

For Linux there's a launcher script, `run_clipboard_sanitizer.sh`, that
activates the venv in its folder and starts the program:

```bash
chmod +x run_clipboard_sanitizer.sh
./run_clipboard_sanitizer.sh
```

`clipboard-sanitizer.desktop` is an example menu entry for it. **Edit the
`Exec=` line** to the path where you saved the program (it currently has
the author's own path), then copy it to `~/.local/share/applications/`.


## Notes

Details, details...

### Buttons

| Button | Action |
|---|---|
| Start / Stop Monitoring | Pauses and resumes clipboard monitoring |
| Save Settings | Saves the current options in `settings.json` (next to the program) |
| Clear Log | Clears the output log |

Options take effect as soon as you change them, but they are only kept for
the next start if you click **Save Settings**.

If `settings.json` is missing or broken, defaults are used.


### Options

Left column (text changes):

- **Strip to one line** (default on)
  - Keeps only the first line of the clipboard text. Turn off to let
    multi-line text pass through (it is still cleaned of forbidden characters).
- **Remove emoji**
- **Non-Latin to end**
  - Moves non-Latin-script text (and numbers / symbols attached to it) from
    the start of the text to the end. Example: a Japanese title in front of
    an English one.
  - Numbers, dates and symbols count as whichever side the nearest letter is
    on.
- **Attach symbols to text** (used by "Non-Latin to end")
  - Keeps symbols (underscores, quotes, ...) attached to whichever side
    (Latin / non-Latin) they're next to. When off, symbols never count as
    Latin, so a leading symbol is moved along with the prefix.
- **Remove trailing symbols**
  - Strips trailing characters that aren't letters, numbers or brackets
    (e.g. `-`, `|`, `=`, `+`), including any spaces between them.
  - Note that `/`, `\` and `|` are turned into `-` before this step, so a title
    ending in ` |` ends in ` -` unless this option is on.
- **Move leading (...) to end**
  - Moves a leading bracketed group to the end, only if it sits at the very
    start. Brackets elsewhere are left as-is. Handles `()`, `[]`, `{}` and
    common CJK brackets. If the whole text is nothing but bracketed groups,
    it's left untouched.
- **Pin quote symbol in place**
  - If the text starts with a quotation mark (converted to `_`), keeps that
    `_` at the very start even if other options would move it.

Right column (ignore / logging / case):

- **Show timestamps** - Prefix each log line with the time (HH:MM).
- **Ignore URLs** - Text starting with `http://` or `https://` is left alone.
- **Ignore file paths** - Absolute file paths are left alone.
- **Ignore checksums** - A text that is just an MD5 (32 hex characters) or
  SHA256 (64 hex characters) checksum is left alone. (Off by default.)
- **Case** (pick one, or none)
  - Lowercase, CAPITALIZE, or Capitalize Each Word.
  - Capitalize Each Word splits at apostrophes, so "don't" becomes "Don'T".

Bottom row:

- **Use separator when moving non-Latin prefix** + separator field
  - Inserts the separator between the text and the moved prefix. The field
    is applied when you finish editing (press Enter or click away).


### Order of operations

Strip to one line, remove emoji, replace forbidden characters, pin quote
symbol, move leading (...), non-Latin to end, remove trailing symbols, case.

A log line starting with ↻ means the text was re-processed because you changed
an option.


## Known limitations

- Only text is handled. Images and files copied from a file manager are
  ignored.
- Copying the exact same text twice in a row doesn't trigger a new
  sanitization (the clipboard hasn't changed).
- When text is changed, the clipboard is overwritten with the sanitized text.
- The clipboard is checked ten times per second.


## License

MIT License. See the [LICENSE](LICENSE) file.

Copyright (c) 2026 Ragnar Aronsen


## Version history

- 2026.11.23.1
             - Options section is collapsible (collapsed at start), window
               slightly shorter.
             - Monitoring starts automatically at launch, and existing
               clipboard text is sanitized when monitoring starts.
             - Fix: "Remove trailing symbols" left a trailing "-" or " -" in
               some cases (e.g. "Title - |"), which only disappeared when
               the text was processed a second time.
             - Version number in the title bar is now "(raron YYYY.MM.DD.x)",
               x being the day's version.
