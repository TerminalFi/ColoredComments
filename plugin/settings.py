import re
from collections import OrderedDict

import sublime

from . import logger as log

default_tags = {
    "Important": {
        "scope": "comments.important",
        "identifier": "!",
        "underline": False,
        "stippled_underline": False,
        "squiggly_underline": False,
        "outline": False,
        "is_regex": False,
        "ignorecase": True,
    },
    "Deprecated": {
        "scope": "comments.deprecated",
        "identifier": "*",
    },
    "Question": {
        "scope": "comments.question",
        "identifier": "?",
    },
    "TODO": {
        "scope": "comments.todo",
        "identifier": "TODO[:]?|todo[:]?",
        "is_regex": True,
        "ignorecase": True,
    },
    "FIXME": {
        "scope": "comments.fixme",
        "identifier": "FIXME[:]?|fixme[:]?",
        "is_regex": True
    },
    "UNDEFINED": {
        "scope": "comments.undefined",
        "identifier": "//[:]?",
        "is_regex": True
    }
}


class Settings(object):
    def __init__(self) -> None:
        self.debug = False
        self.continued_matching = True
        self.continued_matching_pattern = "-"
        self.comment_icon_enabled = True
        self.comment_icon = "dots"
        self.disabled_syntax = list()
        self.tags = dict()
        self.tag_regex = OrderedDict()
        self.region_keys = list()

    def get_icon(self) -> str:
        if self.comment_icon_enabled:
            return self.comment_icon
        return ""

    def get_regex(self, identifier: str) -> re.Pattern:
        return self.tag_regex.get(identifier)

    def get_matching_pattern(self):
        return self.continued_matching_pattern

    def get_flags(self, tag: dict) -> int:
        options = {
            "outline": sublime.DRAW_NO_FILL,
            "underline": sublime.DRAW_SOLID_UNDERLINE,
            "stippled_underline": sublime.DRAW_STIPPLED_UNDERLINE,
            "squiggly_underline": sublime.DRAW_SQUIGGLY_UNDERLINE,
            "persistent": sublime.PERSISTENT,
        }
        flags = 0
        for index, option in options.items():
            if tag.get(index) is True:
                flags |= option
        return flags

    def get_scope_for_region(self, key: str, tag: dict) -> str:
        if tag.get("scope"):
            return tag.get("scope")
        scope_name = f"comments.{key.lower()}"
        return scope_name.replace(" ", ".").lower()


_settings_obj = None
settings = Settings()


def load_settings() -> None:
    global _settings_obj
    settings_obj = sublime.load_settings("colored_comments.sublime-settings")
    _settings_obj = settings_obj
    update_settings(settings, settings_obj)
    settings_obj.add_on_change(
        "_on_updated_settings", lambda: update_settings(settings, settings_obj)
    )


def unload_settings() -> None:
    if _settings_obj:
        _settings_obj.clear_on_change("_on_updated_settings")


def get_boolean_setting(
    settings_obj: sublime.Settings, key: str, default: bool
) -> bool:
    val = settings_obj.get(key)
    if isinstance(val, bool):
        return val
    else:
        return default


def get_dictionary_setting(
    settings_obj: sublime.Settings, key: str, default: dict
) -> dict:
    val = settings_obj.get(key)
    if isinstance(val, dict):
        return val
    else:
        return default


def get_list_setting(settings_obj: sublime.Settings, key: str, default: list) -> list:
    val = settings_obj.get(key)
    if isinstance(val, list):
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
    settings.continued_matching = get_boolean_setting(
        settings_obj, "continued_matching", True
    )
    settings.continued_matching_pattern = get_str_setting(
        settings_obj, "continued_matching_pattern", "-"
    )
    settings.comment_icon_enabled = get_boolean_setting(
        settings_obj, "comment_icon_enabled", True
    )
    settings.comment_icon = "Packages/Colored Comments/icons/{}.png".format(
        get_str_setting(settings_obj, "comment_icon", "dots")
    )
    settings.disabled_syntax = get_list_setting(
        settings_obj, "disabled_syntax", [
            "Packages/Text/Plain text.tmLanguage"]
    )
    settings.tags = get_dict_setting(settings_obj, "tags", default_tags)
    settings.tag_regex = _generate_identifier_expression(settings.tags)
    settings.region_keys = _generate_region_keys(settings.tags)


def _generate_region_keys(tags: dict) -> list:
    region_keys = list()
    for key in tags:
        if key.lower() not in region_keys:
            region_keys.append(key.lower())
    return region_keys


def escape_regex(pattern: str) -> str:
    pattern = re.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


def _generate_identifier_expression(tags: dict) -> OrderedDict:
    unordered_tags = dict()
    identifiers = OrderedDict()
    for key, value in tags.items():
        priority = 2147483647
        if value.get("priority", False):
            tag_priority = value.get("priority")
            try:
                tag_priority = int(priority)
                priority = tag_priority
            except ValueError as ex:
                log.debug(
                    f"[Colored Comments]: {_generate_identifier_expression.__name__} - {ex}"
                )
        unordered_tags.setdefault(priority, list()).append(
            {"name": key, "settings": value}
        )
    for key in sorted(unordered_tags):
        for tag in unordered_tags.get(key):
            tag_identifier = ["^("]
            tag_identifier.append(
                tag.get("settings").get("identifier")
                if tag.get("settings").get("is_regex", False)
                else escape_regex(tag.get("settings").get("identifier"))
            )
            tag_identifier.append(")[ \t]+(?:.*)")
            flag = re.I if tag.get("settings").get("ignorecase", False) else 0
            identifiers[tag.get("name")] = re.compile(
                "".join(tag_identifier), flags=flag
            )
    return identifiers
