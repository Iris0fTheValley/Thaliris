`merge_config(base, override)` in `config.py` is used to layer user settings over defaults, but it overwrites whole nested sections and mutates the defaults. Fix it.

Nested dictionaries are merged recursively: keys only in `base` are kept, keys in `override` win, and a nested dict in `override` is merged into the matching nested dict in `base`. Any other value (including lists and `None`) in `override` simply replaces the base value. Neither input may be modified, and the returned dict must not share nested dicts with either input.
