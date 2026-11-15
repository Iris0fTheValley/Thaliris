`load_notes(directory)` in `notes.py` loads notes for a Chinese-speaking team, and it is not reliable yet. Fix and finish it.

It must return `{file_name: text}` for every visible `.txt` file in the directory (skip files whose name starts with a dot). Notes come from different tools: most are UTF-8, some UTF-8 files start with a byte-order mark, and some old files are GBK. Each note must come back correctly decoded: no BOM character left in the text and no replacement characters. File names can contain Chinese characters. The result must not depend on the machine's locale.
