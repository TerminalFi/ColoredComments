import sublime
import sublime_plugin
from .color_manager import ColorManager
import re

NAME = "Colored Comments"
VERSION = "2.0.3"
SETTINGS = dict()
TAG_MAP = dict()


class ColorCommentsEventListener(sublime_plugin.EventListener):
    def on_load_async(self, view):
        view.run_command("colored_comments")

    def on_modified(self, view):
        view.run_command("colored_comments")


class ColoredCommentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if self.view.match_selector(0, "text.plain"):
            return
        global TAG_MAP, SETTINGS
        regions = self.view.find_by_selector("comment - punctuation.definition.comment")

        if SETTINGS.get("prompt_new_color_scheme", True):
            color_scheme_manager = ColorManager(
                "User/Colored Comments", TAG_MAP, SETTINGS, False
            )
            color_scheme_manager.create_user_custom_theme()
        self.ApplyDecorations(
            generate_identifier_expression(TAG_MAP), regions, TAG_MAP, SETTINGS
        )

    def ApplyDecorations(self, delimiter, regions, tags, settings):
        to_decorate = dict()
        identifier_regex = re.compile(delimiter)

        for tag in tags:
            to_decorate[tag] = []

        previous_match = ""
        for region in regions:
            for reg in self.view.split_by_newlines(region):
                reg_text = self.view.substr(reg).strip()
                matches = identifier_regex.search(reg_text)
                if not matches:
                    if len(reg_text) != 0:
                        if (
                            settings.get("continued_matching")
                            and previous_match != ""
                            and reg_text[0] == "-"
                        ):
                            to_decorate[previous_match] += [reg]
                        else:
                            previous_match = ""
                    continue

                for tag in tags:
                    if tags[tag]["identifier"] != matches.group(1):
                        continue
                    previous_match = tag
                    to_decorate[tag] += [reg]

            for value in to_decorate:
                if value not in tags.keys():
                    continue

                decorations = tags[value]

                flags = sublime.PERSISTENT
                if "outline" in decorations.keys() and decorations["outline"] is True:
                    flags |= sublime.DRAW_NO_FILL

                if (
                    "underline" in decorations.keys()
                    and decorations["underline"] is True
                ):
                    flags |= sublime.DRAW_SOLID_UNDERLINE

                if (
                    "stippled_underline" in decorations.keys()
                    and decorations["stippled_underline"] is True
                ):
                    flags |= sublime.DRAW_STIPPLED_UNDERLINE

                if (
                    "squiggly_underline" in decorations.keys()
                    and decorations["squiggly_underline"] is True
                ):
                    flags |= sublime.DRAW_SQUIGGLY_UNDERLINE

                scope_to_use = ""
                if "scope" in decorations.keys():
                    scope_to_use = decorations["scope"]
                else:
                    scope_to_use = (
                        "colored.comments.color."
                        + decorations["color"]["name"].replace(" ", ".").lower()
                    )

                self.view.add_regions(
                    value, to_decorate[value], scope_to_use, "dot", flags
                )


class ColoredCommentsThemeGeneratorCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global TAG_MAP, SETTINGS
        get_settings()
        color_scheme_manager = ColorManager(
            "User/Colored Comments", TAG_MAP, SETTINGS, True
        )
        color_scheme_manager.create_user_custom_theme()


class ColoredCommentsThemeRevertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global SETTINGS
        get_settings()
        preferences = sublime.load_settings("Preferences.sublime-settings")
        preferences.set("color_scheme", SETTINGS.get("old_color_scheme", ""))
        sublime.save_settings("Preferences.sublime-settings")


def escape_regex(pattern):
    pattern = re.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


def generate_identifier_expression(tags):
    identifiers = list()
    for tag in tags:
        identifiers.append(tags[tag]["identifier"])

    identifier_regex = "^("
    identifier_regex += "|".join(escape_regex(ident) for ident in identifiers)
    identifier_regex += ")+[ \t]+(?:.*)"
    return identifier_regex


def get_settings():
    global TAG_MAP, SETTINGS
    SETTINGS = sublime.load_settings("colored_comments.sublime-settings")
    TAG_MAP = SETTINGS.get("tags", [])


def plugin_loaded():
    get_settings()
