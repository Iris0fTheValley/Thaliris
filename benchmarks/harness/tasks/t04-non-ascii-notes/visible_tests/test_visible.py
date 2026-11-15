import os
import tempfile
import unittest

from notes import load_notes


class VisibleTests(unittest.TestCase):
    def test_utf8_chinese_note_and_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "会议记录.txt"), "wb") as fh:
                fh.write("今天的会议很顺利".encode("utf-8"))
            with open(os.path.join(tmp, "plain.txt"), "wb") as fh:
                fh.write(b"hello")
            self.assertEqual(
                load_notes(tmp), {"会议记录.txt": "今天的会议很顺利", "plain.txt": "hello"}
            )

    def test_skips_dotfiles_and_other_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in (".secret.txt", "image.png", "keep.txt"):
                with open(os.path.join(tmp, name), "wb") as fh:
                    fh.write(b"x")
            self.assertEqual(sorted(load_notes(tmp)), ["keep.txt"])
