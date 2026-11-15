"""Load plain-text notes from a directory."""
import os


def load_notes(directory):
    """Return {file_name: text} for every .txt file in ``directory``."""
    notes = {}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".txt"):
            with open(os.path.join(directory, name)) as handle:
                notes[name] = handle.read()
    return notes
