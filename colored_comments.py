import sublime
import sublime_plugin
import sys


SCOPES = [
    "string",
    "entity.name.class",
    "variable.parameter",
    "invalid.deprecated",
    "invalid",
    "support.function",
]

ST3 = False if sys.version_info < (3, 0) else True
USE_REGEX = False
IGNORE_CASE = False
WHOLE_WORD = False  # only effective when USE_REGEX is True
TAG_MAP = []
IDENTIFIERS = list()
IDENTIFIER_REGEX = ""


single_line_regex = r"^(?:[\t ]+)?({{SINGLE_PLACEHOLDER}}[^\n]*)"
# (?:^|[ \t])(?:MULTI_LINE_BEGIN[\s])+([\s\S]*?)(?:MULTI_LINE_END) - Non Matching
multi_line_regex = r"(^|[ \t])({{MULTI_LINE_BEGIN}}[\s])+([\s\S]*?)({{MULTI_LINE_END}})"

# generate_identifier_expression will return the regex required
# to properly capture the identifiers for highlighting
def generate_identifier_expression():
    IDENTIFIER_REGEX = "("
    IDENTIFIER_REGEX += "|".join(IDENTIFIERS)
    IDENTIFIER_REGEX += ")+(.*)"
    return IDENTIFIER_REGEX


class ColoredCommentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        print(get_settings().get("tags", []))


def get_settings():
    global USE_REGEX, IGNORE_CASE, WHOLE_WORD, SCOPES, TAG_MAP
    setting = sublime.load_settings("colored_comments.sublime-settings")
    USE_REGEX = setting.get("use_regex", False)
    IGNORE_CASE = setting.get("ignore_case", False)
    WHOLE_WORD = setting.get("whole_word", False)
    SCOPES = setting.get("colors_by_scope", SCOPES)
    TAG_MAP = setting.get("tags", [])
    return setting
