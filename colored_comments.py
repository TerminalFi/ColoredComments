import re
from collections import OrderedDict

import sublime
import sublime_plugin

from .plugin import load_settings
from .plugin import logger as log
from .plugin import settings, unload_settings
from .plugin.color_manager import ColorManager

NAME = "Colored Comments"
VERSION = "3.0.1"

region_keys = list()
tag_regex = OrderedDict()
icon = str()
color_scheme_manager = ColorManager

icon_path = "Packages/Colored Comments/icons"
settings_path = "colored_comments.sublime-settings"
comment_selector = "comment - punctuation.definition.comment"


class ColoredCommentsEventListener(sublime_plugin.EventListener):
    def on_init(self, views):
        for view in views:
            view.run_command("colored_comments")

    def on_load_async(self, view):
        view.run_command("colored_comments")

    def on_modified_async(self, view):
        view.run_command("colored_comments")


class ColoredCommentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global tag_regex
        self.tag_regex = tag_regex

        if self.view.match_selector(0, "text.plain"):
            return

        self.ClearDecorations()
        self.ApplyDecorations()

    def ClearDecorations(self):
        for region_key in region_keys:
            self.view.erase_regions(region_key)

    def ApplyDecorations(self):
        to_decorate = dict()
        prev_match = str()
        for region in self.view.find_by_selector(comment_selector):
            for reg in self.view.split_by_newlines(region):
                line = self.view.substr(reg)
                if not settings.continued_matching_pattern.startswith(" "):
                    line = line.strip()
                for tag_identifier in self.tag_regex:
                    matches = self.tag_regex.get(tag_identifier).search(
                        line.strip()
                    )
                    if not matches:
                        if (
                            settings.continued_matching
                            and prev_match
                            and line
                            and line.startswith(settings.continued_matching_pattern)
                        ):
                            to_decorate.setdefault(prev_match, []).append(reg)
                        else:
                            prev_match = str()
                        continue
                    prev_match = tag_identifier
                    to_decorate.setdefault(tag_identifier, []).append(reg)
                    break

            for key in to_decorate:
                tag = settings.get("tags", []).get(key)
                self.view.add_regions(
                    key=key.lower(),
                    regions=to_decorate.get(key),
                    scope=_get_scope_for_region(tag),
                    icon=icon,
                    flags=self._get_tag_flags(tag),
                )

    def _get_tag_flags(self, tag):
        options = {
            "outline": sublime.DRAW_NO_FILL,
            "underline": sublime.DRAW_SOLID_UNDERLINE,
            "stippled_underline": sublime.DRAW_STIPPLED_UNDERLINE,
            "squiggly_underline": sublime.DRAW_SQUIGGLY_UNDERLINE,
        }
        flags = sublime.PERSISTENT
        for index, option in options.items():
            if index in tag.keys() and tag[index] is True:
                flags |= option
        return flags


class ColoredCommentsThemeGeneratorCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        color_scheme_manager.create_user_custom_theme()


class ColoredCommentsThemeRevertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        preferences = sublime.load_settings("Preferences.sublime-settings")
        if preferences.get("color_scheme"):
            color_scheme_manager.remove_override(
                preferences.get("color_scheme"))


def _get_scope_for_region(tag: dict) -> str:
    if tag.get("scope"):
        return tag.get("scope")
    scope_name = "colored.comments.color.{}".format(
        tag.get("color").get("name"))
    return scope_name.replace(" ", ".").lower()


def escape_regex(pattern):
    pattern = re.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


def _generate_identifier_expression(tags):
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
                    "[Colored Comments]: {} - {}".format(
                        _generate_identifier_expression.__name__, ex
                    )
                )
        unordered_tags.setdefault(priority, list()).append(
            {"name": key, "settings": value}
        )
    for key in sorted(unordered_tags):
        for tag in unordered_tags[key]:
            tag_identifier = ["^("]
            tag_identifier.append(
                tag["settings"]["identifier"]
                if tag["settings"].get("is_regex", False)
                else escape_regex(tag["settings"]["identifier"])
            )
            tag_identifier.append(")[ \t]+(?:.*)")
            flag = re.I if tag["settings"].get("ignorecase", False) else 0
            identifiers[tag["name"]] = re.compile(
                "".join(tag_identifier), flags=flag
            )
    return identifiers


def _generate_region_keys(region_keys, tag_map):
    for key in tag_map:
        if key.lower() not in region_keys:
            region_keys.append(key.lower())


# def load_settings():
#     global settings, continued_matching, continued_matching_pattern
#     settings = sublime.load_settings(settings_path)
#     continued_matching = settings.get("continued_matching", False)
#     continued_matching_pattern = settings.get(
#         "continued_matching_pattern", "-")


def plugin_loaded():
    global settings, tag_regex, region_keys
    global icon, color_scheme_manager
    load_settings()

    tag_regex = _generate_identifier_expression(settings.tags)
    _generate_region_keys(region_keys, settings.tags)
    icon = settings.icon

    log.set_debug_logging(settings.debug)

    color_scheme_manager = ColorManager(
        tags=settings.tags
    )


def plugin_unloaded():
    unload_settings()
