# Colored Comments

A powerful Sublime Text plugin for creating more readable and organized comments throughout your code. Colored Comments allows you to highlight different types of comments with custom colors, search across your entire project for tagged comments, and maintain code documentation standards.

The plugin was heavily inspired by [Better Comments by aaron-bond](https://github.com/aaron-bond/better-comments) but has been completely rewritten with modern async architecture and enhanced functionality.

## ✨ Features

- **🎨 Colorful Comment Highlighting** - Automatically highlight comments based on configurable tags
- **🔍 Project-wide Tag Search** - Quickly find all TODO, FIXME, and custom tags across your entire project
- **⚡ Async Performance** - Non-blocking file scanning with optimized batch processing
- **🎯 Smart Preview** - Preview tag locations without losing your current position
- **📋 Enhanced Quick Panel** - Rich HTML formatting with emojis and file context
- **⚙️ Fully Configurable** - Customize everything from tags to file scanning behavior
- **🔄 Continuation Support** - Continue highlighting across multiple comment lines
- **🚀 Modern Architecture** - Built with async/await and optimized for large projects

## 🚀 Quick Start

1. Install the plugin via Package Control
2. Add comment tags to your code:
   ```python
   # TODO: Implement user authentication
   # FIXME: Fix memory leak in data processing
   # ! Important: This affects security
   # ? Question: Should we cache this result?
   ```
3. Use `Ctrl+Shift+P` → "Colored Comments: List All Tags" to search your project
4. Customize tags and colors in your settings

## 📖 Available Commands

| Command | Description | Default Keybinding |
|---------|-------------|-------------------|
| `Colored Comments: GoTo Comment` | Command to list tag indicated comments across entire project | - |
| `Colored Comments: List All Tags` | Similar to GoTo Comment, but limited to specific tags | - |
| `Colored Comments: Edit Color Scheme` | Open color scheme editor with template | - |
| `Colored Comments: Show Debug Logs` | View debug information | - |

## ⚙️ Configuration

### Global Settings

Configure the plugin by editing `Preferences` → `Package Settings` → `Colored Comments` → `Settings`:

```jsonc
{
    // Enable debug logging
    "debug": false,
    
    // Enables continued matching of the previous tag
    "continued_matching": true,
    
    // Character to continue matching on
    "continued_matching_pattern": "-",
    
    // Automatically continue highlighting based on previous line
    "auto_continue_highlight": false,
    
    // Delay in milliseconds before applying decorations (debounce)
    "debounce_delay": 300,
    
    // Shows comment icon next to comments
    "comment_icon_enabled": false,
    
    // Which comment icon to use (comment, dots)
    "comment_icon": "dots",
    
    // Syntax files to ignore
    "disabled_syntax": [
        "Packages/Text/Plain text.tmLanguage",
        "Packages/Markdown/MultiMarkdown.sublime-syntax"
    ]
}
```

### Continued Matching

When enabled, comments can span multiple lines with continuation:

```python
# TODO: Implement user authentication system
# - Check password strength requirements
# - Add two-factor authentication support
# - Integrate with OAuth providers
# This comment won't be highlighted (no continuation marker)
```

### File Scanning Settings

Control which files are scanned during project-wide tag searches:

```jsonc
{
    // File extensions to skip when scanning for tags
    "skip_extensions": [
        ".pyc", ".class", ".exe", ".dll", ".zip", ".jpg", ".mp4", ".pdf"
    ],
    
    // Directory names to skip when scanning
    "skip_dirs": [
        "__pycache__", ".git", "node_modules", ".vscode", "build", "dist"
    ]
}
```

## 🏷️ Tag Configuration

### Default Tags

The plugin comes with these default tags:

| Tag | Identifier | Description | Emoji |
|-----|------------|-------------|-------|
| **TODO** | `TODO:?` or `todo:?` | Tasks to be completed | 📋 |
| **FIXME** | `FIXME:?` or `fixme:?` | Code that needs fixing | 🔧 |
| **Important** | `!` | Critical information | ⚠️ |
| **Question** | `?` | Questions or uncertainties | ❓ |
| **Deprecated** | `*` | Deprecated code | ⚠️ |
| **UNDEFINED** | `//:?` | Placeholder comments | ❔ |

### Custom Tags

Add your own tags or override defaults:

```jsonc
{
    "tags": {
        "NOTE": {
            "scope": "comments.note",
            "identifier": "NOTE[:]?|note[:]?",
            "is_regex": true,
            "ignorecase": true,
            "icon_emoji": "📝"
        },
        "HACK": {
            "scope": "comments.hack",
            "identifier": "HACK[:]?|hack[:]?",
            "is_regex": true,
            "icon_emoji": "🔨",
            "outline": true
        }
    }
}
```

### Tag Properties

Each tag supports these properties:

- **`identifier`** - Text or regex pattern to match (required)
- **`is_regex`** - Set to `true` if identifier is a regex pattern
- **`ignorecase`** - Case-insensitive matching
- **`scope`** - Color scheme scope name
- **`icon_emoji`** - Emoji shown in quick panel and previews
- **`underline`** - Enable solid underline
- **`stippled_underline`** - Enable stippled underline  
- **`squiggly_underline`** - Enable squiggly underline
- **`outline`** - Enable outline only (no background fill)
- **`priority`** - Matching priority (lower numbers = higher priority)

### Advanced Tag Examples

```jsonc
{
    "tags": {
        // Simple plaintext tag
        "BUG": {
            "identifier": "BUG:",
            "scope": "comments.bug",
            "icon_emoji": "🐛"
        },
        
        // Regex tag with high priority
        "CRITICAL": {
            "identifier": "CRITICAL[!]*:?",
            "is_regex": true,
            "priority": -1,
            "scope": "comments.critical",
            "icon_emoji": "🚨",
            "outline": true,
            "underline": true
        },
        
        // Case-sensitive tag
        "API": {
            "identifier": "API:",
            "ignorecase": false,
            "scope": "comments.api",
            "icon_emoji": "🔌"
        }
    }
}
```

## 🎨 Color Scheme Integration

### Automatic Template Injection

When you use "Edit Color Scheme", the plugin automatically injects comment color definitions:

```jsonc
{
    "rules": [
        {
            "name": "Comments: TODO",
            "scope": "comments.todo",
            "foreground": "var(bluish)"
        },
        {
            "name": "Comments: FIXME", 
            "scope": "comments.fixme",
            "foreground": "var(redish)"
        },
        {
            "name": "Comments: Important",
            "scope": "comments.important", 
            "foreground": "var(orangish)"
        }
        // ... more comment styles
    ]
}
```

### Built-in Color Variables

Use these predefined color variables in your color scheme:

- `var(redish)` - Red tones
- `var(orangish)` - Orange tones  
- `var(yellowish)` - Yellow tones
- `var(greenish)` - Green tones
- `var(bluish)` - Blue tones
- `var(purplish)` - Purple tones
- `var(pinkish)` - Pink tones
- `var(cyanish)` - Cyan tones

## 🔍 Tag Search Features

### Project-wide Search

Search for tags across your entire project with advanced filtering:

1. **All Tags**: `Ctrl+Shift+P` → "Colored Comments: List All Tags"
2. **Filtered Search**: Choose specific tag types from the input handler
3. **Current File Only**: Search only the active file

### Rich Quick Panel

The search results show:
- **Tag Type** with emoji icon
- **File Location** with relative path
- **Line Number** and preview
- **Syntax Highlighting** in preview
- **HTML Formatting** for better readability

### Preview Navigation

- **Preview Mode** - Hover over results to preview without navigation
- **Transient Views** - Quick preview without opening permanent tabs
- **Position Restoration** - Return to original position when canceling
- **Smart Navigation** - Jump to exact line and column

## 🚀 Performance Features

### Async Architecture
- **Non-blocking** file scanning
- **Batch processing** for large projects
- **Debounced updates** to prevent excessive processing
- **Smart caching** of comment regions

### Optimized File Scanning
- **Heuristic detection** of text files
- **Configurable filtering** to skip binary files
- **Directory exclusion** for faster scanning
- **Progress reporting** during large scans

### Memory Efficiency
- **Lazy loading** of file contents
- **Temporary views** for unopened files  
- **Cleanup routines** to prevent memory leaks
- **Optimized data structures** for large projects

## 🛠️ Development & Debugging

### Debug Mode

Enable debug logging to troubleshoot issues:

```jsonc
{
    "debug": true
}
```

Then use "Colored Comments: Show Debug Logs" to view detailed information about:
- Tag regex compilation
- File scanning progress
- Comment region detection
- Performance metrics

### Contributing

The plugin welcomes contributions! Key areas:

- **Tag patterns** for new languages
- **Color scheme templates** 
- **Performance optimizations**
- **UI/UX improvements**

## 🙏 Credits

- Inspired by [Better Comments by aaron-bond](https://github.com/aaron-bond/better-comments)
- Built on [sublime_aio](https://github.com/packagecontrol/sublime_aio) for async support
- Uses [sublime_lib](https://github.com/SublimeText/sublime_lib) for enhanced functionality

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
