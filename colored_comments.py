import sublime
import sublime_plugin
import os
import re


TAG_MAP = list()
SYNTAX_MAP = list
IDENTIFIERS = list()


single_line_regex = r"^(?:[\t ]+)?([SINGLE_PLACEHOLDER][^\n]*)"
multi_line_regex = r"(?:^|[ \t])(?:[MULTI_BEGIN][\s])+([\s\S]*?)(?:[MULTI_END])"


class ColorCommentsEventListener(sublime_plugin.EventListener):
    def on_load_async(self, view):
        view.run_command("colored_comments")

    def on_modified(self, view):
        view.run_command("colored_comments")


class ColoredCommentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global SYNTAX_MAP
        get_settings()
        syntax = get_syntax(self.view.settings().get("syntax"))
        if syntax not in SYNTAX_MAP.keys():
            print('unsupported syntax detected ("%s")' % syntax)

        # isMulti = (
        #     SYNTAX_MAP[syntax]["multi"] if "multi" in SYNTAX_MAP[syntax].keys() else []
        # )
        single = SYNTAX_MAP[syntax]["single"]
        single_regex = single_line_regex.replace(
            "[SINGLE_PLACEHOLDER]", escape_regex(single)
        )
        regions = self.view.find_all(single_regex)
        # if get_settings().get("multiline", False) and isMulti != []:
        #     ccRegex = multi_line_regex.replace(
        #         "[MULTI_BEGIN]", escape_regex(isMulti[0])
        #     )
        #     ccRegex = ccRegex.replace("[MULTI_END]", escape_regex(isMulti[1]))
        #     regions += self.view.find_all(ccRegex)

        self.ApplyDecorations(
            generate_identifier_expression(escape_regex(single)), regions
        )

        return

    def ApplyDecorations(self, delimiter, regions):
        global TAG_MAP
        to_decorate = {"BAD_ENTRY_COLORED_COMMENTS": []}
        identifier_regex = re.compile(delimiter)

        for tag in TAG_MAP:
            to_decorate[tag] = []

        for region in regions:
            region_length = len(region)
            if region_length < 3:
                print("no formating required")
                continue

            matches = identifier_regex.search(self.view.substr(region))
            if matches:
                for tag in TAG_MAP:
                    if TAG_MAP[tag]["identifier"] != matches.group(1):
                        continue
                    to_decorate[tag] += [region]

        for value in to_decorate:
            if value not in TAG_MAP.keys():
                continue

            decorations = TAG_MAP[value]
            flags = 0
            if "style" not in decorations.keys() or decorations["style"] not in (
                "outline",
                "underline",
            ):
                flags |= sublime.DRAW_SOLID_UNDERLINE
                flags |= sublime.DRAW_NO_OUTLINE
                flags |= sublime.DRAW_NO_FILL
            elif decorations["style"] == "underline":
                flags |= sublime.DRAW_SOLID_UNDERLINE
                flags |= sublime.DRAW_NO_OUTLINE
                flags |= sublime.DRAW_NO_FILL
            else:
                flags |= sublime.DRAW_NO_FILL
            self.view.add_regions(
                value, to_decorate[value], decorations["scope"], "dot", flags
            )


# Escape the patterns
def escape_regex(pattern):
    pattern = re.escape(pattern)
    for character in "'<>`":
        pattern = pattern.replace("\\" + character, character)
    return pattern


# Returns the current syntax of the file
def get_syntax(syntaxPath):
    return os.path.splitext(syntaxPath)[0].split("/")[-1].lower()


# generate_identifier_expression will return the regex required
# to properly capture the identifiers for highlighting
def generate_identifier_expression(delimiter):
    global TAG_MAP
    identifiers = list()
    for tag in TAG_MAP:
        identifiers.append(TAG_MAP[tag]["identifier"])
    identifier_regex = "(?:" + delimiter + ")+(?: |\\t)*"
    identifier_regex += "("
    identifier_regex += "|".join(escape_regex(ident) for ident in identifiers)
    identifier_regex += ")+(?:.*)"
    return identifier_regex


def get_settings():
    global TAG_MAP, SYNTAX_MAP
    setting = sublime.load_settings("colored_comments.sublime-settings")
    TAG_MAP = setting.get("tags", [])
    SYNTAX_MAP = setting.get("syntax", [])
    return setting
