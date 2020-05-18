import sublime
import sublime_plugin

from .plugin import logger as log
from .plugin.color_manager import ColorManager
from .plugin.settings import load_settings, settings, unload_settings

NAME = "Colored Comments"
VERSION = "3.0.1"

region_keys = list()
color_scheme_manager = ColorManager

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
        if self.view.settings().get("syntax") in settings.disabled_syntax:
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
                for tag_identifier in settings.tag_regex:
                    matches = settings.tag_regex.get(tag_identifier).search(
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
                tag = settings.tags.get(key)
                self.view.add_regions(
                    key=key.lower(),
                    regions=to_decorate.get(key),
                    scope=_get_scope_for_region(tag),
                    icon=settings.comment_icon if settings.comment_icon_enabled else "",
                    flags=self._get_flags(tag),
                )

    def _get_flags(self, tag):
        options = {
            "outline": sublime.DRAW_NO_FILL,
            "underline": sublime.DRAW_SOLID_UNDERLINE,
            "stippled_underline": sublime.DRAW_STIPPLED_UNDERLINE,
            "squiggly_underline": sublime.DRAW_SQUIGGLY_UNDERLINE,
        }
        flags = sublime.PERSISTENT
        for index, option in options.items():
            if tag.get(index) is True:
                flags |= option
        return flags


class ColoredCommentsClearCommand(ColoredCommentsCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        self.ClearDecorations()


class ColoredCommentsThemeGeneratorCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        color_scheme_manager.tags = settings.tags
        color_scheme_manager.create_user_custom_theme()


class ColoredCommentsThemeRevertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        preferences = sublime.load_settings("Preferences.sublime-settings")
        if preferences.get("color_scheme"):
            color_scheme_manager.remove_override(preferences.get("color_scheme"))


def _get_scope_for_region(tag: dict) -> str:
    if tag.get("scope"):
        return tag.get("scope")
    scope_name = "colored.comments.color.{}".format(tag.get("color").get("name"))
    return scope_name.replace(" ", ".").lower()


def _generate_region_keys(region_keys, tag_map):
    for key in tag_map:
        if key.lower() not in region_keys:
            region_keys.append(key.lower())


def plugin_loaded():
    global region_keys
    global color_scheme_manager
    load_settings()
    _generate_region_keys(region_keys, settings.tags)
    log.set_debug_logging(settings.debug)

    color_scheme_manager = ColorManager(tags=settings.tags)


def plugin_unloaded():
    unload_settings()
