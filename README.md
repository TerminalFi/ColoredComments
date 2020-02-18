# ColoredComments
The ColoredComments plugin was designed to help create more readible comments throughout your code. It was heavily inspired by [Better Comments by aaron-bond
](https://github.com/aaron-bond/better-comments)

## New Syntaxs
Adding a new supported language is easy. Just add the following to the settings file and it will be automatically be included. The below is a sample settings for actionscript. Modify it based on your language needs.

```json
 "actionscript":
        {
            "single": "//",
            "multi":["/*", "*/"]
        },
```