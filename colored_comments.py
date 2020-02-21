import sublime
import sublime_plugin
import re


TAG_MAP = dict()


class ColorCommentsEventListener(sublime_plugin.EventListener):
    def on_load_async(self, view):
        view.run_command("colored_comments")

    def on_modified(self, view):
        view.run_command("colored_comments")


class ColoredCommentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        get_settings()
        regions = self.view.find_by_selector("comment - punctuation.definition.comment")
        self.ApplyDecorations(generate_identifier_expression(), regions)
        return

    def ApplyDecorations(self, delimiter, regions):
        global TAG_MAP
        to_decorate = {"BAD_ENTRY_COLORED_COMMENTS": []}
        identifier_regex = re.compile(delimiter)

        for tag in TAG_MAP:
            to_decorate[tag] = []

        previous_match = ""
        for region in regions:
            for reg in self.view.split_by_newlines(region):
                reg_text = self.view.substr(reg).strip()
                matches = identifier_regex.search(reg_text)
                if not matches:
                    if len(reg_text) == 0:
                        continue

                    if (
                        get_settings().get("continued_matching")
                        and previous_match != ""
                        and reg_text[0] == "-"
                    ):
                        to_decorate[previous_match] += [reg]
                    else:
                        previous_match = ""
                    continue

                for tag in TAG_MAP:
                    if TAG_MAP[tag]["identifier"] != matches.group(1):
                        continue
                    previous_match = tag
                    to_decorate[tag] += [reg]

            for value in to_decorate:
                if value not in TAG_MAP.keys():
                    continue

                decorations = TAG_MAP[value]

                # * Default to outline
                flags = sublime.DRAW_NO_FILL
                if "style" not in decorations.keys():
                    flags |= sublime.DRAW_SOLID_UNDERLINE
                    flags |= sublime.DRAW_NO_OUTLINE
                elif decorations["style"] == "underline":
                    flags |= sublime.DRAW_SOLID_UNDERLINE
                    flags |= sublime.DRAW_NO_OUTLINE
                elif decorations["style"] == "stippled_underline":
                    flags |= sublime.DRAW_STIPPLED_UNDERLINE
                    flags |= sublime.DRAW_NO_OUTLINE
                self.view.add_regions(
                    value, to_decorate[value], decorations["scope"], "dot", flags
                )


def escape_regex(pattern):
    pattern = re.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


def generate_identifier_expression():
    global TAG_MAP
    identifiers = list()
    for tag in TAG_MAP:
        identifiers.append(TAG_MAP[tag]["identifier"])

    identifier_regex = "^("
    identifier_regex += "|".join(escape_regex(ident) for ident in identifiers)
    identifier_regex += ")+[ \t]+(?:.*)"
    return identifier_regex


def get_settings():
    global TAG_MAP
    setting = sublime.load_settings("colored_comments.sublime-settings")
    TAG_MAP = setting.get("tags", [])
    return setting
