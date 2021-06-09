import sublime
import sublime_plugin

from .plugin import logger as log
from .lib.sublime_lib import ResourcePath
from .plugin.settings import load_settings, settings, unload_settings

NAME = "Colored Comments"
VERSION = "3.0.4"

comment_selector = "comment - punctuation.definition.comment"

# Thanks PackageDev
SCHEME_TEMPLATE = """\
{
  // http://www.sublimetext.com/docs/3/color_schemes.html
  "variables": {
    "important_comment": "var(region.redish)",
    "deprecated_comment": "var(region.purplish)",
    "question_comment": "var(region.cyanish)",
    "todo_comment": "var(region.greenish)",
    "fixme_comment": "var(region.bluish)",
    "undefined_comment": "var(region.accent)",
  },
  "globals": {
    // "foreground": "var(green)",
  },
  "rules": [
    {
      "name": "IMPORTANT COMMENTS",
      "scope": "comments.important",
      "foreground": "var(important_comment)",
      "background": "rgba(1,22,38, 0.1)",
    },
    {
      "name": "DEPRECATED COMMENTS",
      "scope": "comments.deprecated",
      "foreground": "var(deprecated_comment)",
      "background": "rgba(1,22,38, 0.1)",
    },
    {
      "name": "QUESTION COMMENTS",
      "scope": "comments.question",
      "foreground": "var(question_comment)",
      "background": "rgba(1,22,38, 0.1)",
    },
    {
      "name": "TODO COMMENTS",
      "scope": "comments.todo",
      "foreground": "var(todo_comment)",
      "background": "rgba(1,22,38, 0.1)",
    },
    {
      "name": "FIXME COMMENTS",
      "scope": "comments.fixme",
      "foreground": "var(fixme_comment)",
      "background": "rgba(1,22,38, 0.1)",
    },
    {
      "name": "UNDEFINED COMMENTS",
      "scope": "comments.undefined",
      "foreground": "var(undefined_comment)",
      "background": "rgba(1,22,38, 0.1)",
    },
  ],
}""".replace("  ", "\t")

KIND_SCHEME = (sublime.KIND_ID_VARIABLE, "s", "Scheme")
DEFAULT_CS = 'Packages/Color Scheme - Default/Mariana.sublime-color-scheme'


class ColoredCommentsEditSchemeCommand(sublime_plugin.WindowCommand):

    """Like syntax-specific settings but for the currently used color scheme."""

    def run(self):
        view = self.window.active_view()
        if not view:
            return

        scheme_path = self.get_scheme_path(view, 'color_scheme')
        if scheme_path != 'auto':
            self.open_scheme(scheme_path)
        else:
            paths = [
                (setting, self.get_scheme_path(view, setting))
                for setting in ('dark_color_scheme', 'light_color_scheme')
            ]
            choices = [
                sublime.QuickPanelItem(
                    setting, details=str(path), kind=KIND_SCHEME)
                for setting, path in paths
            ]

            def on_done(i):
                if i >= 0:
                    self.open_scheme(paths[i][1])

            self.window.show_quick_panel(choices, on_done)

    @staticmethod
    def get_scheme_path(view, setting_name):
        # Be lazy here and don't consider invalid values
        scheme_setting = view.settings().get(setting_name, DEFAULT_CS)
        if scheme_setting == 'auto':
            return 'auto'
        elif "/" not in scheme_setting:
            return ResourcePath.glob_resources(scheme_setting)[0]
        else:
            return ResourcePath(scheme_setting)

    def open_scheme(self, scheme_path):
        self.window.run_command(
            'edit_settings',
            {
                'base_file': '/'.join(("${packages}",) + scheme_path.parts[1:]),
                'user_file': "${packages}/User/" + scheme_path.stem + '.sublime-color-scheme',
                'default': SCHEME_TEMPLATE,
            },
        )


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
                    scope=settings.get_scope_for_region(key, tag),
                    icon=settings.get_icon(),
                    flags=settings.get_flags(tag),
                )


class ColoredCommentsClearCommand(ColoredCommentsCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        self.ClearDecorations()


def plugin_loaded() -> None:
    load_settings()
    log.set_debug_logging(settings.debug)


def plugin_unloaded() -> None:
    unload_settings()
