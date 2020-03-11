import sublime
import sublime_plugin
from .color_manager import ColorManager
import regex
import collections

NAME = "Colored Comments"
VERSION = "2.0.4"
SETTINGS = dict()
TAG_MAP = dict()
TAG_REGEX = ""


# ? Is there a better was to implement this
class ColorCommentsEventListener(sublime_plugin.EventListener):
    def on_load(self, view):
        view.run_command("colored_comments")

    def on_modified(self, view):
        view.run_command("colored_comments")


class ColoredCommentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if self.view.match_selector(0, "text.plain"):
            return
        global TAG_MAP, SETTINGS, TAG_REGEX
        get_settings()

        comment_selector = "comment - punctuation.definition.comment"
        regions = self.view.find_by_selector(comment_selector)

        if SETTINGS.get("prompt_new_color_scheme", True):
            color_scheme_manager = ColorManager(
                "User/Colored Comments", TAG_MAP, SETTINGS, False
            )
            color_scheme_manager.create_user_custom_theme()
        self.ApplyDecorations(TAG_REGEX, regions, TAG_MAP, SETTINGS)

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
                flags = self.get_tag_flags(sel_tag)
                scope_to_use = ""
                if "scope" in sel_tag.keys():
                    scope_to_use = sel_tag["scope"]
                else:
                    scope_to_use = (
                        "colored.comments.color."
                        + sel_tag["color"]["name"].replace(" ", ".").lower()
                    )

                self.view.add_regions(
                    value, to_decorate[value], scope_to_use, "", flags
                )

    def get_tag_flags(self, tag):
        options = {
            "outline": sublime.DRAW_NO_FILL,
            "underline": sublime.DRAW_SOLID_UNDERLINE,
            "stippled_underline": sublime.DRAW_STIPPLED_UNDERLINE,
            "squiggly_underline": sublime.DRAW_SQUIGGLY_UNDERLINE,
        }
        flags = sublime.PERSISTENT
        for key, value in options.items():
            if key in tag.keys() and tag[key] is True:
                flags |= value
        return flags


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
    global TAG_REGEX
    identifiers = collections.deque([])
    for tag in tags:
        identifiers.append(escape_regex(tags[tag]["identifier"]))
    TAG_REGEX = "(?b)^("
    TAG_REGEX += "|".join(identifiers)
    TAG_REGEX += ")[ \t]+(?:.*)"
    TAG_REGEX = regex.compile(TAG_REGEX)


def get_settings():
    global TAG_MAP, SETTINGS
    SETTINGS = sublime.load_settings("colored_comments.sublime-settings")
    TAG_MAP = SETTINGS.get("tags", [])


def plugin_loaded():
    get_settings()
    global TAG_MAP
    generate_identifier_expression(TAG_MAP)


def plugin_unloaded():
    preferences = sublime.load_settings("Preferences.sublime-settings")
    cc_preferences = sublime.load_settings("colored_comments.sublime-settings")
    old_color_scheme = cc_preferences.get("old_color_scheme", "")
    if old_color_scheme != "":
        preferences.set("color_scheme", old_color_scheme)
    else:
        preferences.erase("color_scheme")
    sublime.save_settings("Preferences.sublime-settings")
