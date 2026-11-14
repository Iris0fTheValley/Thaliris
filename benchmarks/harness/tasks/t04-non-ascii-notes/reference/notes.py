"""Load plain-text notes from a directory."""
import os


def _decode(raw):
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("gbk")


def load_notes(directory):
    """Return {file_name: text} for every visible .txt file in ``directory``."""
    notes = {}
    for name in sorted(os.listdir(directory)):
        if name.startswith(".") or not name.endswith(".txt"):
            continue
        with open(os.path.join(directory, name), "rb") as handle:
            notes[name] = _decode(handle.read())
    return notes
