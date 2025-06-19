import re
from collections import OrderedDict

import sublime

from . import logger as log
class Settings(object):
    def __init__(self) -> None:
        self.debug = False
        self.continued_matching = True
        self.continued_matching_pattern = "-"
        self.auto_continue_highlight = False
        self.debounce_delay = 300  # Debounce delay in milliseconds
        self.comment_icon_enabled = True
        self.comment_icon = "dots"
        self.disabled_syntax = list()
        self.tags = dict()
        self.tag_regex = OrderedDict()
        self.region_keys = list()
        
        # File scanning settings
        self.skip_extensions = set()
        self.skip_dirs = set()
        self.text_extensions = set()

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

    def get_icon_emoji(self, tag_name: str) -> str:
        """Get the emoji icon for a tag, with fallback to a default emoji."""
        if tag_name in self.tags:
            tag = self.tags[tag_name]
            return tag.get("icon_emoji", "💬")
        return "💬"


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


def get_int_setting(settings_obj: sublime.Settings, key: str, default: int) -> int:
    """Get an integer setting with fallback.
    
    Args:
        settings_obj: The settings object to fetch from
        key: The setting key
        default: The default value if not found or wrong type
        
    Returns:
        int: The setting value or default
    """
    val = settings_obj.get(key)
    if isinstance(val, int):
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
    settings.auto_continue_highlight = get_boolean_setting(
        settings_obj, "auto_continue_highlight", False
    )
    settings.debounce_delay = get_int_setting(
        settings_obj, "debounce_delay", 300
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
    
    # File scanning settings
    skip_extensions_list = get_list_setting(settings_obj, "skip_extensions", [])
    settings.skip_extensions = set(ext.lower() for ext in skip_extensions_list)
    
    skip_dirs_list = get_list_setting(settings_obj, "skip_dirs", [])
    settings.skip_dirs = set(skip_dirs_list)

    log.debug(f"File scanning settings loaded:")
    log.debug(f"  Skip extensions: {len(settings.skip_extensions)} items")
    log.debug(f"  Skip directories: {len(settings.skip_dirs)} items")
    
    # Handle tag merging: default_tags + tags
    # Users can set "default_tags": {} to disable all defaults
    # Users can set "tags": {} to have no additional tags
    user_default_tags = get_dict_setting(settings_obj, "default_tags", {})
    user_custom_tags = get_dict_setting(settings_obj, "tags", {})
    
    # Log tag loading information
    log.debug(f"Loading default tags: {list(user_default_tags.keys())}")
    log.debug(f"Loading custom tags: {list(user_custom_tags.keys())}")
    
    # Merge default tags with custom tags (custom tags override defaults with same name)
    merged_tags = {}
    merged_tags.update(user_default_tags)
    
    # Track overrides for logging
    overridden_tags = []
    for tag_name, tag_config in user_custom_tags.items():
        if tag_name in merged_tags:
            overridden_tags.append(tag_name)
        merged_tags[tag_name] = tag_config
    
    if overridden_tags:
        log.debug(f"Custom tags overriding defaults: {overridden_tags}")
    
    log.debug(f"Final merged tags: {list(merged_tags.keys())}")
    
    settings.tags = merged_tags
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
