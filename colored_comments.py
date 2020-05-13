import logging
import re
import sys
from collections import OrderedDict

import sublime
import sublime_plugin

from .plugin.color_manager import ColorManager

NAME = "Colored Comments"
VERSION = "3.0.0"

log = logging.Logger
region_keys = list()
settings = dict()
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
        global settings, tag_regex
        self.settings = settings
        self.tag_regex = tag_regex
        self.regions = self.view.find_by_selector(comment_selector)

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
        for region in self.regions:
            for reg in self.view.split_by_newlines(region):
                line = self.view.substr(reg)
                continued_matching_pattern = settings.get(
                    "continued_matching_pattern", "-")
                if not continued_matching_pattern.startswith(" "):
                    line = line.strip()
                for tag_identifier in self.tag_regex:
                    matches = self.tag_regex.get(tag_identifier).search(
                        line.strip()
                    )
                    if not matches:
                        if (
                            settings.get("continued_matching", False)
                            and prev_match
                            and line
                            and line.startswith(continued_matching_pattern)
                        ):
                            to_decorate.setdefault(prev_match, []).append(reg)
                        else:
                            prev_match = str()
                        continue
                    prev_match = tag_identifier
                    to_decorate.setdefault(tag_identifier, []).append(reg)
                    break

            for key in to_decorate:
                sel_tag = self.settings.get("tags", []).get(key)
                flags = self._get_tag_flags(sel_tag)
                scope_to_use = ""
                if sel_tag.get("scope"):
                    scope_to_use = sel_tag.get("scope")
                else:
                    scope_to_use = (
                        "colored.comments.color.{}".format(
                            sel_tag["color"]["name"].replace(" ", ".").lower())
                    )
                self.view.add_regions(
                    key=key.lower(),
                    regions=to_decorate.get(key),
                    scope=scope_to_use,
                    icon=icon,
                    flags=flags,
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


def _get_icon():
    icon = str()
    if settings.get("comment_icon_enabled", False):
        icon = settings.get("comment_icon", "dots")
        try:
            icon = "%s/%s.png" % (icon_path, icon)
            sublime.load_binary_resource(icon)
        except OSError as ex:
            log.debug(
                "[Colored Comments]: {} - {}".format(_get_icon.__name__, ex))
            icon = str()
            pass
    return icon


def load_settings():
    global settings, continued_matching, continued_matching_pattern
    settings = sublime.load_settings(settings_path)
    continued_matching = settings.get("continued_matching", False)
    continued_matching_pattern = settings.get(
        "continued_matching_pattern", "-")


def setup_logging():
    global log
    log = logging.getLogger("colored_comments")
    out_hdlr = logging.StreamHandler(sys.stdout)
    out_hdlr.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    out_hdlr.setLevel(logging.DEBUG)
    log.addHandler(out_hdlr)


def plugin_loaded():
    global tag_regex, region_keys
    global log, icon, color_scheme_manager
    load_settings()
    setup_logging()

    tag_regex = _generate_identifier_expression(settings.get("tags", []))
    _generate_region_keys(region_keys, settings.get("tags", []))
    icon = _get_icon()

    if settings.get("debug", False):
        log.setLevel(logging.DEBUG)
    color_scheme_manager = ColorManager(
        tags=settings.get("tags", []),
        log=log,
    )
