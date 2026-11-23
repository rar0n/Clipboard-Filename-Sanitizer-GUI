#!/bin/bash
# Launcher for Clipboard Sanitizer GUI.
# Activates the venv in this folder and runs the app.
# Place this script and clipboard_sanitizer_gui.py in the same folder,
# then create the venv once with:
#   python3 -m venv venv
#   source venv/bin/activate
#   pip install -r requirements.txt
#   deactivate

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ -f "$DIR/venv/bin/activate" ]; then
    source "$DIR/venv/bin/activate"
fi

python3 "$DIR/clipboard_sanitizer_gui.py"
