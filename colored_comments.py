import logging
import sys
from collections import OrderedDict
from os import path

import regex

import sublime
import sublime_plugin

from .color_manager import ColorManager

NAME = "Colored Comments"
VERSION = "2.3.0"

log = logging.Logger
REGION_KEYS = list()
SETTINGS = dict()
TAG_MAP = dict()
TAG_REGEX = OrderedDict()
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
        global SETTINGS, TAG_MAP, TAG_REGEX, REGION_KEYS
        self.settings = SETTINGS
        self.tag_map = TAG_MAP
        self.region_keys = REGION_KEYS
        self.tag_regex = TAG_REGEX

        if self.view.match_selector(0, "text.plain"):
            return

        regions = self.view.find_by_selector(comment_selector)
        if self.settings.get("prompt_new_color_scheme", False):
            if color_scheme_manager.update_preferences:
                color_scheme_manager.create_user_custom_theme()

        self.ClearDecorations(regions)
        self.ApplyDecorations(regions)

    def ClearDecorations(self, regions):
        if not regions:
            for region_key in self.region_keys:
                self.view.erase_regions(region_key)

    def ApplyDecorations(self, regions):
        to_decorate = dict()

        for tag in self.tag_map:
            to_decorate[tag] = []

        previous_match = ""
        for region in regions:
            for reg in self.view.split_by_newlines(region):
                line = self.view.substr(reg).strip()
                for tag_identifier in self.tag_regex:
                    matches = self.tag_regex[tag_identifier].search(line)
                    if not matches:
                        if (
                            len(line) != 0
                            and self.settings.get("continued_matching")
                            and previous_match != ""
                            # todo Customizable Setting
                            # - Implement a way to customiz
                            # - this setting via the settings ss
                            # - files
                            and line[0] == "-"
                        ):
                            to_decorate[previous_match] += [reg]
                        else:
                            previous_match = ""
                        continue
                    previous_match = tag_identifier
                    to_decorate[tag_identifier] += [reg]
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
                if key.lower() not in self.region_keys:
                    self.region_keys.append(key.lower())
                icon = _get_icon()
                if icon is not None:
                    self.view.add_regions(
                        key=key.lower(),
                        regions=to_decorate[key],
                        scope=scope_to_use,
                        icon=icon,
                        flags=flags,
                    )
                else:
                    self.view.add_regions(
                        key=key.lower(),
                        regions=to_decorate[key],
                        scope=scope_to_use,
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
        self.settings = SETTINGS
        self.tag_map = TAG_MAP

        color_scheme_manager.update_preferences = True
        color_scheme_manager.regenerate = True
        color_scheme_manager.create_user_custom_theme()


class ColoredCommentsThemeRevertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.settings = SETTINGS

        preferences = sublime.load_settings("Preferences.sublime-settings")
        old_color_scheme = self.settings.get("old_color_scheme", "")
        if old_color_scheme == "" or not path.exists(old_color_scheme):
            preferences.erase("color_scheme")
        else:
            preferences.set("color_scheme", old_color_scheme)
        sublime.save_settings("Preferences.sublime-settings")
        self.settings.erase("old_color_scheme")
        sublime.save_settings(settings_path)


def escape_regex(pattern):
    pattern = regex.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


def generate_identifier_expression(tags):
    unordered_tags = dict()
    ordered_tags = OrderedDict()
    identifiers = OrderedDict()
    for key, value in tags.items():
        priority = 2147483647
        if value.get("priority", False):
            priority = value.get("priority")
            try:
                priority = int(priority)
            except ValueError as ex:
                log.debug(
                    "[Colored Comments]: %s - %s"
                    % (generate_identifier_expression.__name__, ex)
                )
                priority = 2147483647
        if not unordered_tags.get(priority, False):
            unordered_tags[priority] = list()
        unordered_tags[priority] += [{"name": key, "settings": value}]
    for key in sorted(unordered_tags):
        ordered_tags[key] = unordered_tags[key]

    for key, value in ordered_tags.items():
        for tag in value:
            tag_identifier = "^("
            tag_identifier += (
                tag["settings"]["identifier"]
                if tag["settings"].get("is_regex", False)
                else escape_regex(tag["settings"]["identifier"])
            )
            tag_identifier += ")[ \t]+(?:.*)"
            identifiers[tag["name"]] = regex.compile(tag_identifier)
    return identifiers


def _get_icon():
    icon = None
    if SETTINGS.get("comment_icon_enabled", False):
        icon = SETTINGS.get("comment_icon", "dots")
        try:
            icon = "%s/%s.png" % (icon_path, icon)
            sublime.load_binary_resource(icon)
        except OSError as ex:
            log.debug("%s" % ex)
            icon = None
            pass
    return icon


def load_settings():
    global TAG_MAP, SETTINGS
    SETTINGS = sublime.load_settings(settings_path)
    TAG_MAP = SETTINGS.get("tags", [])


def setup_logging():
    global log
    log = logging.getLogger(__name__)
    out_hdlr = logging.StreamHandler(sys.stdout)
    out_hdlr.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    out_hdlr.setLevel(logging.DEBUG)
    log.addHandler(out_hdlr)


def plugin_loaded():
    global log
    load_settings()
    global TAG_REGEX, color_scheme_manager, TAG_MAP, SETTINGS
    TAG_REGEX = generate_identifier_expression(TAG_MAP)
    setup_logging()
    if SETTINGS.get("debug", False):
        log.setLevel(logging.DEBUG)

    color_scheme_manager = ColorManager(
        new_color_scheme_path=scheme_path,
        tags=TAG_MAP,
        settings=SETTINGS,
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
