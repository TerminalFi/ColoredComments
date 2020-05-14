import sublime

default_tags = {
        "Important":
        {
            "identifier": "!",
            "underline": False,
            "stippled_underline": False,
            "squiggly_underline": False,
            "outline": False,
            "is_regex": False,
            "ignorecase": True,
            "color":
            {
                "name": "important",
                "foreground": "#FF2D00",
                "background": "rgba(1,22,38, 0.1)"
            },
        },
        "Deprecated":
        {
            "identifier": "*",
            "color":
            {
                "name": "deprecated",
                "foreground": "#98C379",
                "background": "rgba(1,22,38, 0.1)"
            },
        },
        "Question":
        {
            "identifier": "?",
            "color":
            {
                "name": "question",
                "foreground": "#3498DB",
                "background": "rgba(1,22,38, 0.1)"
            },
        },
        "TODO":
        {
            "color":
            {
                "background": "rgba(1,22,38, 0.1)",
                "foreground": "#FF8C00",
                "name": "todo"
            },
            "identifier": "TODO[:]?|todo[:]?",
            "is_regex": True,
            "ignorecase": True,
        },
        "FIXME":
        {
            "color":
            {
                "background": "rgba(1,22,38, 0.1)",
                "foreground": "#9933FF",
                "name": "fixme"
            },
            "identifier": "FIXME[:]?|fixme[:]?",
            "is_regex": True
        },
        "UNDEFINED":
        {
            "color":
            {
                "background": "rgba(1,22,38, 0.1)",
                "foreground": "#474747",
                "name": "undefined"
            },
            "identifier": "//[:]?",
            "is_regex": True
        }}


class Settings(object):

    def __init__(self) -> None:
        self.debug = False
        self.continued_matching = True
        self.continued_matching_pattern = "-"
        self.comment_icon_enabled = True
        self.comment_icon = "dots"
        self.tags = dict()


_settings_obj = None
settings = Settings()


def load_settings() -> None:
    global _settings_obj
    settings_obj = sublime.load_settings("LSP.sublime-settings")
    _settings_obj = settings_obj
    update_settings(settings, settings_obj)
    settings_obj.add_on_change("_on_updated_settings", lambda: update_settings(settings, settings_obj))


def unload_settings() -> None:
    if _settings_obj:
        _settings_obj.clear_on_change("_on_updated_settings")


def get_boolean_setting(settings_obj: sublime.Settings, key: str, default: bool) -> bool:
    val = settings_obj.get(key)
    if isinstance(val, bool):
        return val
    else:
        return default


def get_dictionary_setting(settings_obj: sublime.Settings, key: str, default: dict) -> dict:
    val = settings_obj.get(key)
    if isinstance(val, dict):
        return val
    else:
        return default


def get_str_setting(settings_obj: sublime.Settings, key: str, default: str) -> str:
    val = settings_obj.get(key)
    if isinstance(val, str):
        return val
    else:
        return default


def get_dict_setting(settings_obj: sublime.Settings, key: str, default: dict) -> dict:
    val = settings_obj.get(key)
    if isinstance(val, dict):
        return val
    else:
        return default


def update_settings(settings: Settings, settings_obj: sublime.Settings) -> None:
    settings.debug = get_boolean_setting(settings_obj, "debug", True)
    settings.continued_matching = get_boolean_setting(settings_obj, "continued_matching", True)
    settings.continued_matching_pattern = get_str_setting(settings_obj, "continued_matching_pattern", "-")
    settings.comment_icon_enabled = get_boolean_setting(settings_obj, "comment_icon_enabled", True)
    settings.comment_icon = get_str_setting(settings_obj, "comment_icon", "dots")
    settings.tags = get_dict_setting(settings_obj, "tags", default_tags)
