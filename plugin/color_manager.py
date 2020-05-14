import os

import sublime


sublime_settings = "Preferences.sublime-settings"
override_path = "Colored Comments Override"
scope_name = "colored.comments.color."


class ColorManager:
    def __init__(self, tags):
        self.tags = tags

    def remove_override(self, scheme):
        self.save_scheme(os.path.basename(scheme), {"rules": [], "variables": {}})

    def create_user_custom_theme(self):
        if not self.tags:
            return

        self.sublime_pref = sublime.load_settings(sublime_settings)
        color_scheme = self.sublime_pref.get("color_scheme")
        scheme_content = self._add_colors_to_scheme({"rules": [], "variables": {}})
        self.save_scheme(os.path.basename(color_scheme), scheme_content)

    def save_scheme(self, scheme_name: str, scheme_content: dict) -> None:
        user_override_path = _build_scheme_path(os.path.basename(scheme_name))
        with open(user_override_path, "w") as outfile:
            outfile.write(sublime.encode_value(scheme_content, True))

    def _add_colors_to_scheme(self, scheme_content: dict) -> dict:
        rules = scheme_content.get("rules")
        for tag in self.tags:
            if not self.tags.get(tag) and not self.tags.get(tag).get("color"):
                continue

            name = _get_color_property("name", self.tags.get(tag))
            background = _get_color_property("background", self.tags.get(tag))
            foreground = _get_color_property("foreground", self.tags.get(tag))
            if False in [name, background, foreground]:
                continue

            scope = "{}{}".format(scope_name, name.lower().replace(" ", "."))
            if not any(rule.get("scope") == scope for rule in rules):
                entry = {
                            "name": "[Colored Comments] {}".format(name.title()),
                            "scope": scope,
                            "foreground": foreground,
                            "background": background
                        }
                rules.append(entry)
        scheme_content["rules"] = rules
        return scheme_content


def _build_scheme_path(scheme: str) -> str:
    _create_override_path()
    return os.path.join(sublime.packages_path(), override_path, scheme)


def _create_override_path() -> None:
    return os.makedirs(os.path.join(sublime.packages_path(), override_path), exist_ok=True)


def _get_color_property(property: str, tags: dict) -> str:
    if not tags.get("color") and tags.get("color").get(property, False):
        return False
    return tags.get("color").get(property)
