"""
Templates used by the Colored Comments plugin.
"""

# Color scheme template for comments highlighting
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

