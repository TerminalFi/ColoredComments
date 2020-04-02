import logging
import os
import sys
from collections import OrderedDict
from os import path

import regex

import sublime
import sublime_plugin

from .color_manager import ColorManager

NAME = "Colored Comments"
VERSION = "2.3.3"

log = logging.Logger
region_keys = list()
settings = dict()
tag_map = dict()
tag_regex = OrderedDict()
continued_matching = bool()
icon = str()
color_scheme_manager = ColorManager

scheme_path = "User/Colored Comments"
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
        global settings, tag_map, tag_regex, region_keys
        self.settings = settings
        self.tag_map = tag_map
        self.region_keys = region_keys
        self.tag_regex = tag_regex
        self.regions = self.view.find_by_selector(comment_selector)

        if self.view.match_selector(0, "text.plain"):
            return

        if self.settings.get("prompt_new_color_scheme", False):
            if color_scheme_manager.update_preferences:
                color_scheme_manager.create_user_custom_theme()

        self.ClearDecorations()
        self.ApplyDecorations()

    def ClearDecorations(self):
        for region_key in self.region_keys:
            self.view.erase_regions(region_key)

    def ApplyDecorations(self):
        to_decorate = dict()
        prev_match = str()
        for region in self.regions:
            for reg in self.view.split_by_newlines(region):
                line = self.view.substr(reg).strip()
                for tag_identifier in self.tag_regex:
                    matches = self.tag_regex[tag_identifier].search(line)
                    if not matches:
                        if (
                            continued_matching
                            and prev_match
                            and line
                            # todo Customizable settings
                            # - Implement a way to customize
                            # - this setting via the settings
                            and line[0] == "-"
                        ):
                            to_decorate.setdefault(prev_match, []).append(reg)
                        else:
                            prev_match = str()
                        continue
                    prev_match = tag_identifier
                    to_decorate.setdefault(tag_identifier, []).append(reg)
                    break

            for key in to_decorate:
                sel_tag = self.tag_map[key]
                flags = self._get_tag_flags(sel_tag)
                scope_to_use = ""
                if "scope" in sel_tag.keys():
                    scope_to_use = sel_tag["scope"]
                else:
                    scope_to_use = (
                        "colored.comments.color."
                        + sel_tag["color"]["name"].replace(" ", ".").lower()
                    )
                self.view.add_regions(
                    key=key.lower(),
                    regions=to_decorate[key],
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
        global color_scheme_manager
        color_scheme_manager.update_preferences = True
        color_scheme_manager.regenerate = True
        color_scheme_manager.create_user_custom_theme()


class ColoredCommentsThemeRevertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global settings

        preferences = sublime.load_settings("Preferences.sublime-settings")
        old_color_scheme = settings.get("old_color_scheme", "")
        if old_color_scheme == "" or not path.exists(old_color_scheme):
            preferences.erase("color_scheme")
        else:
            preferences.set("color_scheme", old_color_scheme)
        sublime.save_settings("Preferences.sublime-settings")
        settings.erase("old_color_scheme")
        sublime.save_settings(settings_path)


def escape_regex(pattern):
    pattern = regex.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


def generate_identifier_expression(tags):
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
                        generate_identifier_expression.__name__, ex
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
            identifiers[tag["name"]] = regex.compile("".join(tag_identifier))
    return identifiers


def _generate_region_keys(region_keys, tag_map):
    for key in tag_map:
        if key.lower() not in region_keys:
            region_keys.append(key.lower())


def _get_icon():
    icon = None
    if settings.get("comment_icon_enabled", False):
        icon = settings.get("comment_icon", "dots")
        try:
            icon = "%s/%s.png" % (icon_path, icon)
            sublime.load_binary_resource(icon)
        except OSError as ex:
            log.debug("{}".format(ex))
            icon = str()
            pass
    return icon


def load_settings():
    global tag_map, settings, continued_matching
    settings = sublime.load_settings(settings_path)
    tag_map = settings.get("tags", [])
    continued_matching = settings.get("continued_matching", False)


def setup_logging():
    global log
    log = logging.getLogger(__name__)
    out_hdlr = logging.StreamHandler(sys.stdout)
    out_hdlr.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    out_hdlr.setLevel(logging.DEBUG)
    log.addHandler(out_hdlr)


def plugin_loaded():
    global tag_regex, tag_map, region_keys
    global log, icon, color_scheme_manager, settings
    load_settings()
    setup_logging()

    tag_regex = generate_identifier_expression(tag_map)
    _generate_region_keys(region_keys, tag_map)
    icon = _get_icon()

    if settings.get("debug", False):
        log.setLevel(logging.DEBUG)

    sublime_preferences = sublime.load_settings("Preferences.sublime-settings")
    sublime_cs = sublime_preferences.get("color_scheme")
    if os.path.basename(sublime_cs)[0:16] != "Colored Comments":
        settings.set("old_color_scheme", sublime_cs)
        sublime.save_settings("colored_comments.sublime-settings")

    color_scheme_manager = ColorManager(
        new_color_scheme_path=scheme_path,
        tags=tag_map,
        settings=settings,
        regenerate=False,
        log=log,
    )


def plugin_unloaded():
    preferences = sublime.load_settings("Preferences.sublime-settings")
    cc_preferences = sublime.load_settings(settings_path)
    old_color_scheme = cc_preferences.get("old_color_scheme", "")
    if old_color_scheme != "":
        preferences.set("color_scheme", old_color_scheme)
    else:
        preferences.erase("color_scheme")
    sublime.save_settings("Preferences.sublime-settings")
