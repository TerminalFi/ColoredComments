import sublime

import os
import sys
import json
from . import plistlib

VERSION = int(sublime.version())


class ColorManager:
    update_preferences = True

    def __init__(self, new_color_scheme_path, tags, settings, regenerate):
        self.new_color_scheme_path = new_color_scheme_path
        self.tags = tags
        self.settings = settings
        self.regenerate = regenerate

    def _add_colors_to_scheme(self, color_scheme_json, is_json):
        settings = (
            color_scheme_json["rules"] if is_json else color_scheme_json["settings"]
        )
        scope_exist = False
        updates_made = False

        for tag in self.tags:
            curr_tag = self.tags[tag]
            if "color" not in curr_tag.keys():
                continue

            color_name = _get_color_name(curr_tag)
            color_background = _get_color_background(curr_tag)
            color_foreground = _get_color_foreground(curr_tag)

            scope = "colored.comments.color."
            scope = scope + color_name.replace(" ", ".").lower()

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
            color_scheme_json["rules"] = settings
        else:
            color_scheme_json["settings"] = settings

        return updates_made, color_scheme_json

    def _create_custom_color_scheme_directory(self):
        package_path = sublime.packages_path()
        path = os.path.join(package_path, self.new_color_scheme_path)

        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def create_user_custom_theme(self):
        if len(self.tags) == 0:
            return

        preferences = sublime.load_settings("Preferences.sublime-settings")
        preferences_cs = preferences.get("color_scheme")
        if self.regenerate:
            if self.settings.get("old_color_scheme", "") != "":
                preferences_cs = self.settings.get("old_color_scheme", "")

        self.settings.set("old_color_scheme", preferences_cs)
        sublime.save_settings("colored_comments.sublime-settings")
        cs_base = os.path.basename(preferences_cs)

        if cs_base[0:16] != "Colored Comments":
            new_cs_base = "Colored Comments-" + cs_base
        else:
            new_cs_base = cs_base

        custom_color_base = self._create_custom_color_scheme_directory()

        new_cs_absolute = os.path.join(custom_color_base, new_cs_base)
        new_cs = "Packages/" + self.new_color_scheme_path + "/" + new_cs_base
        scheme_content = b""
        try:
            scheme_content = sublime.load_binary_resource(preferences_cs)
        except:
            sublime.error_message(
                "An error occured while reading color "
                + "scheme file. Please check the console "
                "for details."
            )
            raise
        updates_made = color_scheme = is_json = ""
        if preferences_cs.endswith(".sublime-color-scheme"):
            is_json = True
            updates_made, color_scheme = self._add_colors_to_scheme(
                json.loads(scheme_content.decode("utf-8")), is_json
            )
        elif preferences_cs.endswith(".tmTheme"):
            is_json = False
            updates_made, color_scheme = self._add_colors_to_scheme(
                plistlib.loads(bytes(scheme_content)), is_json
            )
        else:
            sys.exit(1)

        if self.regenerate:
            print("[Colored Comments] Regenerating theme file")
            try:
                os.remove(new_cs_absolute)
            except:
                pass
            if is_json:
                with open(new_cs_absolute, "w") as outfile:
                    json.dump(color_scheme, outfile, indent=4)
            else:
                with open(new_cs_absolute, "wb") as outfile:
                    outfile.write(plistlib.dumps(color_scheme))

        elif updates_made or preferences_cs != new_cs:
            if is_json:
                with open(new_cs_absolute, "w") as outfile:
                    json.dump(color_scheme, outfile, indent=4)
            else:
                with open(new_cs_absolute, "wb") as outfile:
                    outfile.write(plistlib.dumps(color_scheme))

        if preferences_cs != new_cs:
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
                    preferences.set("color_scheme", new_cs)
                    sublime.save_settings("Preferences.sublime-settings")
                    self.settings.set("prompt_new_color_scheme", False)
                    sublime.save_settings("colored_comments.sublime-settings")
                else:
                    ColorManager.update_preferences = False


def _get_color_name(tags):
    if "color" not in tags.keys():
        return "colored_comments_default"

    if "name" not in tags["color"].keys():
        return "colored_comments_default"
    return tags["color"]["name"]


def _get_color_background(tags):
    if "color" not in tags.keys():
        return "colored_comments_default"

    if "background" not in tags["color"].keys():
        return "colored_comments_default"
    return tags["color"]["background"]


def _get_color_foreground(tags):
    if "color" not in tags.keys():
        return "colored_comments_default"

    if "foreground" not in tags["color"].keys():
        return "colored_comments_default"
    return tags["color"]["foreground"]
