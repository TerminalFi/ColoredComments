# ColoredComments
The ColoredComments plugin was designed to help create more readible comments throughout your code. It was heavily inspired by [Better Comments by aaron-bond
](https://github.com/aaron-bond/better-comments)

## Coming Soon
Currently working on supporting true color customization. No longer will it be restricted to already created scopes/colors. In 2.0.0 expect to see settings similar to the following.

```json
{
    "HELP":
    {
        "identifier": "HELP",
        "background": "#000",
        "foreground": "#00ff66"
        "style": "stippled_underline"
    }
}
```

## Global Settings
The following are global settings for ColoredComments
- **continued_matching** - If enabled, the same match as the previous line will be applied to the next line if prefixed with a `-`

```python
# TODO Highlighted as a TODO
# - This will also be highlighted as a TODO (Prefixed with a -)
# This will be an unhighlighted comment
# ! This is another comment
# - and again, continued highlighting
```

<img width="518" alt="2020-02-21_08-52-51" src="https://user-images.githubusercontent.com/32599364/75039960-c4f61080-5487-11ea-9a43-f9ea7a53842e.png">


## New Highlights
Add new tags easily with the following format. Keep in mind the following:
- **Identifiers**: Are not _regex_, they are plaintext and get inserted into a regex for faster matching
- **Scope**: Are built in colors from your current theme. Changing _Text_ color is current not supported
- **Style**: Style is in reference to how the Comments are displayed. Supported values for style are as follows: "_outline_" (Default if blank), "_underline_", "_stippled_underline_", "_squiggly_underline_"

### Scope Color Examples
Taken from [Sublime MiniHTML Reference](https://www.sublimetext.com/docs/3/minihtml.html#predefined_variables)
- background
- foreground
- accent
- redish
- orangish
- yellowish
- greenish
- cyanish
- bluish
- purplish
- pinkish

### Example Tag
```json
{
    "HELP":
    {
        "identifier": "HELP",
        "scope": "region.bluish",
        "style": "stippled_underline"
    }
}
```

## Contributors
- [TheMilkMan](https://github.com/themilkman)


