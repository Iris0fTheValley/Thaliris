import shlex
import unittest

from cmdbuild import build_command


def roundtrip(program, args):
    return shlex.split(build_command(program, args))


class VisibleTests(unittest.TestCase):
    def test_plain_arguments(self):
        self.assertEqual(roundtrip("ls", ["-l", "src"]), ["ls", "-l", "src"])

    def test_argument_with_spaces(self):
        self.assertEqual(
            roundtrip("cp", ["my file.txt", "backup dir"]), ["cp", "my file.txt", "backup dir"]
        )

    def test_no_arguments(self):
        self.assertEqual(roundtrip("pwd", []), ["pwd"])
