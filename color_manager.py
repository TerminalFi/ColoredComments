import json
import os
import sys

import sublime

from . import plistlib

SUBLIME_SETTINGS = "Preferences.sublime-settings"


class ColorManager:
    update_preferences = True

    def __init__(self, new_color_scheme_path, tags, settings, regenerate, log):
        self.new_color_scheme_path = new_color_scheme_path
        self.tags = tags
        self.settings = settings
        self.regenerate = regenerate
        self.log = log

    def _add_colors_to_scheme(self, color_scheme, is_json):
        settings = color_scheme["rules"] if is_json else color_scheme["settings"]
        scope_exist = False
        updates_made = False

        for tag in self.tags:
            curr_tag = self.tags[tag]
            if "color" not in curr_tag.keys():
                continue

            color_name = _get_color_name(curr_tag)
            color_background = _get_color_background(curr_tag)
            color_foreground = _get_color_foreground(curr_tag)

            scope_name = "colored.comments.color."
            scope = scope_name + color_name.replace(" ", ".").lower()

            for setting in settings:
                if "scope" in setting and setting["scope"] == scope:
                    scope_exist = True
                    break

            if not scope_exist:
                updates_made = True
                entry = {}
                entry["name"] = "[Colored Comments] " + color_name.title()
                entry["scope"] = scope
                if is_json:
                    entry["foreground"] = color_foreground
                    entry["background"] = color_background
                else:
                    entry["settings"] = dict()
                    entry["settings"]["foreground"] = color_foreground
                    entry["settings"]["background"] = color_background

                settings.append(entry)
        if is_json:
            color_scheme["rules"] = settings
        else:
            color_scheme["settings"] = settings

        return updates_made, color_scheme

    def _create_custom_color_scheme_directory(self):
        package_path = sublime.packages_path()
        path = os.path.join(package_path, self.new_color_scheme_path)

        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def create_user_custom_theme(self):
        if len(self.tags) == 0:
            return

        sublime_preferences = sublime.load_settings(SUBLIME_SETTINGS)
        sublime_cs = sublime_preferences.get("color_scheme")
        if self.regenerate:
            if self.settings.get("old_color_scheme", "") != "":
                sublime_cs = self.settings.get("old_color_scheme", "")

        self.settings.set("old_color_scheme", sublime_cs)
        sublime.save_settings("colored_comments.sublime-settings")
        cs_base = os.path.basename(sublime_cs)

        if cs_base[0:16] != "Colored Comments":
            new_cs_base = "Colored Comments-" + cs_base
        else:
            new_cs_base = cs_base

        custom_color_base = self._create_custom_color_scheme_directory()

        new_cs_absolute = os.path.join(custom_color_base, new_cs_base)
        new_cs = "Packages/" + self.new_color_scheme_path + "/" + new_cs_base

        updates_made, color_scheme, is_json = self.load_color_scheme(sublime_cs)

        if self.regenerate:
            self.log.debug(
                "[Colored Comments] : %s - %s",
                self.create_user_custom_theme.__name__,
                "generating / regenerating theme",
            )
            try:
                os.remove(new_cs_absolute)
            except OSError:
                pass
            if is_json:
                with open(new_cs_absolute, "w") as outfile:
                    json.dump(color_scheme, outfile, indent=4)
            else:
                with open(new_cs_absolute, "wb") as outfile:
                    outfile.write(plistlib.dumps(color_scheme))

        elif updates_made or sublime_cs != new_cs:
            if is_json:
                with open(new_cs_absolute, "w") as outfile:
                    json.dump(color_scheme, outfile, indent=4)
            else:
                with open(new_cs_absolute, "wb") as outfile:
                    outfile.write(plistlib.dumps(color_scheme))

        if sublime_cs != new_cs:
            if ColorManager.update_preferences:
                okay = sublime.ok_cancel_dialog(
                    "Would you like to change "
                    + "your color scheme to '"
                    + new_cs
                    + "'? "
                    + "To permanently disable "
                    + "this prompt, set "
                    + "'prompt_new_color_scheme' "
                    + "to false in the Colored Comments settings"
                )

                if okay:
                    sublime_preferences.set("color_scheme", new_cs)
                    sublime.save_settings("Preferences.sublime-settings")
                    self.settings.set("prompt_new_color_scheme", False)
                    sublime.save_settings("colored_comments.sublime-settings")
                else:
                    ColorManager.update_preferences = False

    def load_color_scheme(self, scheme):
        scheme_content = b""
        is_json = False
        try:
            sublime_default_cs = [
                "Mariana.sublime-color-scheme",
                "Celeste.sublime-color-scheme",
                "Monokai.sublime-color-scheme",
                "Breakers.sublime-color-schem",
                "Sixteen.sublime-color-scheme",
            ]
            if scheme in sublime_default_cs:
                scheme = "Packages/Color Scheme - Default/" + scheme
            scheme_content = sublime.load_binary_resource(scheme)
        except Exception as ex:
            sublime.error_message(
                "An error occured while reading color "
                + "scheme file. Please check the console "
                "for details."
            )
            self.log.debug(
                "[Colored Comments] : %s - %s", self.load_color_scheme.__name__, ex
            )
            raise
        updates_made = color_scheme = ""
        if scheme.endswith(".sublime-color-scheme"):
            is_json = True
            updates_made, color_scheme = self._add_colors_to_scheme(
                sublime.decode_value(scheme_content.decode("utf-8")), is_json
            )
        elif scheme.endswith(".tmTheme"):
            is_json = False
            updates_made, color_scheme = self._add_colors_to_scheme(
                plistlib.loads(bytes(scheme_content)), is_json
            )
        else:
            sys.exit(1)
        return updates_made, color_scheme, is_json


def _get_color_name(tags):
    if not tags.get("color", False):
        return "colored_comments_default"

    if not tags["color"].get("name", False):
        return "colored_comments_default"

    return tags["color"]["name"]


def _get_color_background(tags):
    if not tags.get("color", False):
        return "colored_comments_default"

    if not tags["color"].get("background", False):
        return "colored_comments_default"
    return tags["color"]["background"]


def _get_color_foreground(tags):
    if not tags.get("color", False):
        return "colored_comments_default"

    if not tags["color"].get("foreground", False):
        return "colored_comments_default"
    return tags["color"]["foreground"]
