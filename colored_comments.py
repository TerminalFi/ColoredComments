import sublime
import sublime_plugin

from .plugin import logger as log
from .plugin.color_manager import color_manager, load_color_manager
from .plugin.settings import load_settings, settings, unload_settings

NAME = "Colored Comments"
VERSION = "3.0.3"

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

    def ClearDecorations(self) -> None:
        for region_key in settings.region_keys:
            self.view.erase_regions(region_key)

    def ApplyDecorations(self) -> None:
        to_decorate = dict()
        prev_match = str()
        for region in self.view.find_by_selector(comment_selector):
            for reg in self.view.split_by_newlines(region):
                line = self.view.substr(reg)
                if not settings.get_matching_pattern().startswith(" "):
                    line = line.strip()
                for identifier in settings.tag_regex:
                    if not settings.get_regex(identifier).search(line.strip()):
                        if (
                            settings.continued_matching
                            and prev_match
                            and line.startswith(settings.get_matching_pattern())
                        ):
                            to_decorate.setdefault(prev_match, []).append(reg)
                        else:
                            prev_match = str()
                        continue
                    prev_match = identifier
                    to_decorate.setdefault(identifier, []).append(reg)
                    break

            for key in to_decorate:
                tag = settings.tags.get(key)
                self.view.add_regions(
                    key=key.lower(),
                    regions=to_decorate.get(key),
                    scope=settings.get_scope_for_region(tag),
                    icon=settings.get_icon(),
                    flags=settings.get_flags(tag),
                )


class ColoredCommentsClearCommand(ColoredCommentsCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        self.ClearDecorations()


class ColoredCommentsThemeGeneratorCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        color_manager.create_user_custom_theme()


class ColoredCommentsThemeRevertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        preferences = sublime.load_settings("Preferences.sublime-settings")
        if preferences.get("color_scheme"):
            color_manager.remove_override(preferences.get("color_scheme"))


def plugin_loaded() -> None:
    global color_scheme_manager
    load_settings()
    load_color_manager()
    log.set_debug_logging(settings.debug)


def plugin_unloaded() -> None:
    unload_settings()
