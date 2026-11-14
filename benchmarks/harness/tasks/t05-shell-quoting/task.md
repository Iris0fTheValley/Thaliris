`build_command(program, args)` in `cmdbuild.py` builds the command line that our job runner hands to a POSIX shell. It breaks on awkward arguments. Fix it.

The returned string must be split by a POSIX shell back into exactly `[program, *args]`: argument boundaries and content preserved for arguments containing spaces, single or double quotes, `$`, backslashes, newlines, non-ASCII text, and empty strings. Check it with `shlex.split`; do not execute anything.
