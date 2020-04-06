import json
import os
import sys

import sublime

from .lib import plistlib

sublime_settings = "Preferences.sublime-settings"
scope_name = "colored.comments.color."
MSG = """
Would you like to change your color scheme to '$scheme'?
To permanently disable this prompt, set 'prompt_new_color_scheme' 
to false in the Colored Comments settings."""

sublime_default_cs = [
    "Mariana.sublime-color-scheme",
    "Celeste.sublime-color-scheme",
    "Monokai.sublime-color-scheme",
    "Breakers.sublime-color-schem",
    "Sixteen.sublime-color-scheme",
]


class ColorManager:
    def __init__(self, new_color_scheme_path, tags, view, settings, regenerate, log):
        self.new_color_scheme_path = new_color_scheme_path
        self.view = view
        self.sublime_pref = None
        self.tags = tags
        self.settings = settings
        self.regenerate = regenerate
        self.log = log
        self.color_scheme = str()
        self.update_preferences = True
        self.awaiting_feedback = False

    def get_update_pref(self):
        return self.update_preferences

    def get_awaiting_feedback(self):
        return self.awaiting_feedback

    def set_awaiting_feedback(self, status):
        self.awaiting_feedback = status

    def _add_colors_to_scheme(self, color_scheme, is_json):
        scheme_rule_key = "rules" if is_json else "settings"
        settings = color_scheme[scheme_rule_key]
        scope_exist = bool()
        updates = bool()

        for tag in self.tags:
            curr_tag = self.tags[tag]
            if not curr_tag.get("color", False):
                continue

            name = _get_color_property("name", curr_tag)
            background = _get_color_property("background", curr_tag)
            foreground = _get_color_property("foreground", curr_tag)
            if False in [name, background, foreground]:
                continue

            scope = "{}{}".format(scope_name, name.lower().replace(" ", "."))

            for setting in settings:
                if "scope" in setting and setting["scope"] == scope:
                    scope_exist = True

            if not scope_exist:
                updates = True
                entry = dict()
                entry["name"] = "[Colored Comments] {}".format(name.title())
                entry["scope"] = scope
                if is_json:
                    entry["foreground"] = foreground
                    entry["background"] = background
                else:
                    entry["settings"] = dict()
                    entry["settings"]["foreground"] = foreground
                    entry["settings"]["background"] = background

                settings.append(entry)
        color_scheme[scheme_rule_key] = settings
        return updates, color_scheme

    def _create_custom_color_scheme_directory(self):
        path = os.path.join(sublime.packages_path(), self.new_color_scheme_path)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def create_user_custom_theme(self):
        if self.awaiting_feedback:
            return
        self.awaiting_feedback = True
        if not self.tags:
            self.awaiting_feedback = False
            return

        self.sublime_pref = sublime.load_settings(sublime_settings)
        color_scheme = self.sublime_pref.get("color_scheme")
        if self.regenerate and self.settings.get("old_color_scheme", "") != "":
            color_scheme = self.settings.get("old_color_scheme", "")

        self.settings.set("old_color_scheme", color_scheme)
        sublime.save_settings("colored_comments.sublime-settings")
        cs_base = os.path.basename(color_scheme)

        if cs_base[0:16] != "Colored Comments":
            cs_base = "{}{}".format("Colored Comments-", cs_base)

        custom_color_base = self._create_custom_color_scheme_directory()
        new_cs_absolute = os.path.join(custom_color_base, cs_base)
        self.color_scheme = "{}{}{}{}".format(
            "Packages/", self.new_color_scheme_path, "/", cs_base
        )
        print(self.color_scheme)

        updates, loaded_scheme, is_json = self.load_color_scheme(color_scheme)

        if self.regenerate or updates or color_scheme != self.color_scheme:
            try:
                os.remove(new_cs_absolute)
            except OSError as ex:
                self.log.debug(str(ex))
                pass
            if is_json:
                with open(new_cs_absolute, "w") as outfile:
                    json.dump(loaded_scheme, outfile, indent=4)
            else:
                with open(new_cs_absolute, "wb") as outfile:
                    outfile.write(plistlib.dumps(loaded_scheme))

        if color_scheme != self.color_scheme:
            if sublime.ok_cancel_dialog(MSG, "Confirm"):
                self.sublime_pref.set("color_scheme", self.color_scheme)
                sublime.save_settings("Preferences.sublime-settings")
                self.settings.set("prompt_new_color_scheme", False)
                sublime.save_settings("colored_comments.sublime-settings")
            self.update_preferences = False
            self.awaiting_feedback = False

    def load_color_scheme(self, scheme):
        is_json = bool()
        try:
            if scheme in sublime_default_cs:
                scheme = "{}{}".format("Packages/Color Scheme - Default/", scheme)
            scheme_content = sublime.load_binary_resource(scheme)
        except Exception as ex:
            sublime.error_message(
                " ".join(
                    [
                        "An error occured while reading color",
                        "scheme file. Please check the console",
                        "for details.",
                    ]
                )
            )
            self.log.debug(
                "[Colored Comments]: {} - {}".format(
                    self.load_color_scheme.__name__, ex
                )
            )
            raise
        if scheme.endswith(".sublime-color-scheme"):
            is_json = True
            updates, color_scheme = self._add_colors_to_scheme(
                sublime.decode_value(scheme_content.decode("utf-8")), is_json
            )
        elif scheme.endswith(".tmTheme"):
            updates, color_scheme = self._add_colors_to_scheme(
                plistlib.loads(bytes(scheme_content)), is_json
            )
        else:
            sys.exit(1)
        return updates, color_scheme, is_json


def _get_color_property(property, tags):
    if not tags["color"].get(property, False):
        return False
    return tags["color"][property]
