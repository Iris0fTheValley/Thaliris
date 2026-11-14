import shlex
import unittest

from cmdbuild import build_command


def roundtrip(program, args):
    return shlex.split(build_command(program, args))


class HiddenTests(unittest.TestCase):
    def check(self, args, program="echo"):
        self.assertEqual(roundtrip(program, args), [program, *args])

    def test_single_quote(self):
        self.check(["it's here"])

    def test_double_quote(self):
        self.check(['say "hi"'])

    def test_dollar_and_backtick_not_expanded(self):
        self.check(["$HOME", "`id`", "$(whoami)"])

    def test_backslashes(self):
        self.check(["C:\\temp\\new", "a\\ b"])

    def test_empty_string_argument(self):
        self.check(["", "x", ""])

    def test_newline_and_tab(self):
        self.check(["line1\nline2", "a\tb"])

    def test_non_ascii(self):
        self.check(["中文 参数", "café"])

    def test_program_with_space(self):
        self.check(["x"], program="/opt/my tools/run")
