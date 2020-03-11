import sublime
import sublime_plugin
from .color_manager import ColorManager
import regex
import collections

NAME = "Colored Comments"
VERSION = "2.0.3"
SETTINGS = dict()
TAG_MAP = dict()


class ColorCommentsEventListener(sublime_plugin.EventListener):
    def on_load(self, view):
        view.run_command("colored_comments")

    def on_modified(self, view):
        view.run_command("colored_comments")


class ColoredCommentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if self.view.match_selector(0, "text.plain"):
            return
        global TAG_MAP, SETTINGS
        comment_selector = "comment - punctuation.definition.comment"
        regions = self.view.find_by_selector(comment_selector)

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

        for tag in tags:
            to_decorate[tag] = []

        previous_match = ""
        for region in regions:
            for reg in self.view.split_by_newlines(region):
                reg_text = self.view.substr(reg).strip()
                matches = delimiter.search(reg_text)
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
                    identifier = tags[tag]["identifier"]
                    if identifier != matches.group(1):
                        continue
                    previous_match = tag
                    to_decorate[tag] += [reg]

            for value in to_decorate:
                if value not in tags.keys():
                    continue

                sel_tag = tags[value]

                flags = sublime.PERSISTENT
                if "outline" in sel_tag.keys() and sel_tag["outline"] is True:
                    flags |= sublime.DRAW_NO_FILL

                if "underline" in sel_tag.keys() and sel_tag["underline"] is True:
                    flags |= sublime.DRAW_SOLID_UNDERLINE

                if (
                    "stippled_underline" in sel_tag.keys()
                    and sel_tag["stippled_underline"] is True
                ):
                    flags |= sublime.DRAW_STIPPLED_UNDERLINE

                if (
                    "squiggly_underline" in sel_tag.keys()
                    and sel_tag["squiggly_underline"] is True
                ):
                    flags |= sublime.DRAW_SQUIGGLY_UNDERLINE

                scope_to_use = ""
                if "scope" in sel_tag.keys():
                    scope_to_use = sel_tag["scope"]
                else:
                    scope_to_use = (
                        "colored.comments.color."
                        + sel_tag["color"]["name"].replace(" ", ".").lower()
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
        SETTINGS.erase("old_color_scheme")
        sublime.save_settings("colored_comments.sublime-settings")


def escape_regex(pattern):
    pattern = regex.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


def generate_identifier_expression(tags):
    identifiers = collections.deque([])
    for tag in tags:
        identifiers.append(escape_regex(tags[tag]["identifier"]))

    identifier_regex = "(?b)^("
    identifier_regex += "|".join(identifiers)
    identifier_regex += ")[ \t]+(?:.*)"
    return regex.compile(identifier_regex)


def get_settings():
    global TAG_MAP, SETTINGS
    SETTINGS = sublime.load_settings("colored_comments.sublime-settings")
    TAG_MAP = SETTINGS.get("tags", [])


def plugin_loaded():
    get_settings()
