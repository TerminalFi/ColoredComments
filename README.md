# Colored Comments
The Colored Comments plugin was designed to help create more readible comments throughout your code. It was heavily inspired by [Better Comments by aaron-bond
](https://github.com/aaron-bond/better-comments)

# NOTICE !!
If using the new verison run Generate/Regenerate Color Scheme

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

### Version 2+
<img width="461" alt="2020-03-06_21-11-38" src="https://user-images.githubusercontent.com/32599364/76134801-30df8980-5fef-11ea-92b2-ae7155af956b.png">


### Version > 2
<img width="518" alt="2020-02-21_08-52-51" src="https://user-images.githubusercontent.com/32599364/75039960-c4f61080-5487-11ea-9a43-f9ea7a53842e.png">


## New Highlights
Add new tags easily with the following format. Keep in mind the following:

- **identifiers**: These can be _plaintext_ or _regex_ patterns. If they are _regex_ be sure to set the _is_regex_ property to `true`
- **is_regex**: Set this to `true` if your identifier is a _regex_
- **priority**: This setting is critical if you want to prioritize tag settings. **Default**: 2147483647
This should be used if there are multiple tags that could match on the same thing. An example of this would be `"identifier": "*"` and `"identifier": "[\\*]?[ ]?@param"` could both match on `* @param` because one is less precise. To avoid these conflicts you can give the `[\\*]?[ ]?@param` a higher priority such as `"-1"`, Negative values get higher priorty than positive values. If two or more tags get the same priority, they are treated as first come first serve type of matching.
- **Scope**: Are built in colors from your current theme. **_Scope takes precendence over Color_**
- **underline**: Sublime API setting for region draws
- **stippled_underline**: Sublime API setting for region draws
- **squiggly_underline**: Sublime API setting for region draws
- **outline**: Sublime API setting for region draws
- **color**: Custom text colors
    - **name**: This is used when generating the scope for the color scheme
    - **foreground**: This is the **_text_** color
    - **background**: This is the background of the region, generally you'll want this to be your themes _background_ color slightly changed
    _background_ if your themes background is `"rgba(1, 22, 38, 0.0)"` this should be set like `"rgba(1, 22, 38, 0.1)"` for best results


### Scope Examples
Taken from [Sublime MiniHTML Reference](https://www.sublimetext.com/docs/3/minihtml.html#predefined_variables)
- region.background
- region.foreground
- region.accent
- region.redish
- region.orangish
- region.yellowish
- region.greenish
- region.cyanish
- region.bluish
- region.purplish
- region.pinkish

### Example Tag
```json
"Important":
        {
            "identifier": "!",
            "underline": false,
            "stippled_underline": false,
            "squiggly_underline": false,
            "outline": false,
            "color":
            {
                "name": "important",
                "foreground": "#cc0000",
                "background": "rgba(1, 22, 38, 0.1)"
            },
        }
```

## Contributors
- [TheMilkMan](https://github.com/themilkman)


