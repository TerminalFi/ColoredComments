import sublime

import re
import os

import json

VERSION = int(sublime.version())


class ColorManager:
    update_preferences = True
    color_regex = re.compile(
        r"(#([\da-f]{3}){1,2}|(rgb|hsl)a\((\d{1,3}%?,\s?){3}(1|0?\.\d+)\)|(rgb|hsl)\(\d{1,3}%?(,\s?\d{1,3}%?){2}\))$"
    )

    def __init__(self, new_color_scheme_path, tags, settings, regenerate):
        self.new_color_scheme_path = new_color_scheme_path
        self.tags = tags
        self.settings = settings
        self.regenerate = regenerate

    def _add_colors_to_scheme(self, color_scheme_plist):
        settings = color_scheme_plist["rules"]
        scope_exist = False
        updates_made = False

        for tag in self.tags:
            curr_tag = self.tags[tag]
            if "color" not in curr_tag.keys():
                continue

            color_name = _get_color_name(curr_tag)
            color_background = _get_color_background(curr_tag)
            color_foreground = _get_color_foreground(curr_tag)

            if bool(ColorManager.color_regex.search(color_foreground)) is False:
                print(
                    "[Colored Comments]: Invalid color specified - " + color_foreground
                )
                print(
                    "Colors should use a Sublime support format (Hex, RGB, RGBA, HSL, HSLA)"
                )
                color_foreground = "rgb(229, 0, 0)"

            if bool(ColorManager.color_regex.search(color_background)) is False:
                print(
                    "[Colored Comments]: Invalid color specified - " + color_background
                )
                print(
                    "Colors should use a Sublime support format (Hex, RGB, RGBA, HSL, HSLA)"
                )
                color_background = "rgba(255, 255, 255, 0.1)"

            scope = "colored.comments.color." + color_name.replace(" ", ".").lower()

            for setting in settings:
                if "scope" in setting and setting["scope"] == scope and self.regenerate is False:
                    scope_exist = True
                    break

            if not scope_exist:
                updates_made = True
                entry = {}
                entry["name"] = "[Colored Comments] " + color_name.title()
                entry["scope"] = scope
                entry["foreground"] = color_foreground
                entry["background"] = color_background
                settings.append(entry)

        color_scheme_plist["rules"] = settings
        return updates_made, color_scheme_plist

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
        cs_base = os.path.basename(preferences_cs)

        if cs_base[0:15] != "ColoredComments":
            new_cs_base = "ColoredComments-" + cs_base
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
        updates_made, color_scheme = self._add_colors_to_scheme(
            json.loads(scheme_content.decode("utf-8"))
        )
        if self.regenerate:
            print("[Colored Comments] Regenerating theme file")
            with open(new_cs_absolute, "w") as outfile:
                json.dump(color_scheme, outfile, indent=4)
        elif updates_made or preferences_cs != new_cs:
            with open(new_cs_absolute, "w") as outfile:
                json.dump(color_scheme, outfile, indent=4)

        if preferences_cs != new_cs:
            if ColorManager.update_preferences:
                okay = sublime.ok_cancel_dialog(
                    "Would you like to change "
                    + "your color scheme to '"
                    + new_cs
                    + "'? "
                    + "This is "
                    + "where the custom colors "
                    + "are being saved. By "
                    + "clicking cancel you will "
                    + "not be reminded again in "
                    + "this session. "
                    + "To permanently disable "
                    + "this prompt, set "
                    + "'prompt_new_color_scheme' "
                    + "to false in the settings"
                )

                if okay:
                    preferences.set("color_scheme", new_cs)
                    sublime.save_settings("Preferences.sublime-settings")
                    os.sleep(5)
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
