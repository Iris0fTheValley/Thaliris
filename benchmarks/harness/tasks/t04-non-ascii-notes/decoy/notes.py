"""Load plain-text notes from a directory."""
import os


def load_notes(directory):
    """Return {file_name: text} for every visible .txt file in ``directory``."""
    notes = {}
    for name in sorted(os.listdir(directory)):
        if name.startswith(".") or not name.endswith(".txt"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8", errors="replace") as handle:
            notes[name] = handle.read()
    return notes
