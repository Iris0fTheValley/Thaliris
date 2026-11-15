import os
import tempfile
import unittest

from notes import load_notes


def write(tmp, name, data):
    with open(os.path.join(tmp, name), "wb") as fh:
        fh.write(data)


class HiddenTests(unittest.TestCase):
    def test_utf8_bom_is_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "bom.txt", b"\xef\xbb\xbf" + "你好".encode("utf-8"))
            self.assertEqual(load_notes(tmp)["bom.txt"], "你好")

    def test_gbk_note_is_decoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "旧笔记.txt", "你好，世界".encode("gbk"))
            self.assertEqual(load_notes(tmp)["旧笔记.txt"], "你好，世界")

    def test_no_replacement_characters_anywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.txt", "测试一".encode("gbk"))
            write(tmp, "b.txt", "测试二".encode("utf-8"))
            write(tmp, "c.txt", b"\xef\xbb\xbf" + "测试三".encode("utf-8"))
            notes = load_notes(tmp)
            self.assertEqual(notes, {"a.txt": "测试一", "b.txt": "测试二", "c.txt": "测试三"})
            for text in notes.values():
                self.assertNotIn("\ufffd", text)
                self.assertNotIn("\ufeff", text)
