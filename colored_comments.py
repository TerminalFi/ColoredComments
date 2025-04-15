import sublime
import sublime_plugin
import time
import threading
import functools

from .plugin import logger as log
from .lib.sublime_lib import ResourcePath
from .plugin.settings import load_settings, settings, unload_settings
from .templates import SCHEME_TEMPLATE

NAME = "Colored Comments"
VERSION = "3.0.4"

comment_selector = "comment - punctuation.definition.comment"

KIND_SCHEME = (sublime.KIND_ID_VARIABLE, "s", "Scheme")
DEFAULT_CS = 'Packages/Color Scheme - Default/Mariana.sublime-color-scheme'


def debounce(f):
    """Decorator that debounces a function call.
    
    The decorated function will only be executed after the specified delay
    has passed without any new calls. If called again within the delay period,
    the timer is reset.
    
    Args:
        f: The function to debounce
        
    Returns:
        The debounced function
    """
    timers = {}
    
    @functools.wraps(f)
    def wrapped_func(self, *args, **kwargs):
        # Get the instance's unique id (or create a default if not available)
        key = getattr(self, 'view', self).id() if hasattr(self, 'view') else id(self)
        
        # Cancel previous timer if it exists
        if key in timers and timers[key]:
            timers[key].cancel()
            
        # Use the debounce_delay from settings
        def call_function():
            # Remove reference to timer to avoid memory leak
            if key in timers:
                del timers[key]
            # Call the actual function via the main thread to avoid UI issues
            sublime.set_timeout(lambda: f(self, *args, **kwargs), 0)
            
        # Create and store the new timer
        timers[key] = threading.Timer(settings.debounce_delay / 1000.0, call_function)
        timers[key].start()
        
    # Add a cleanup method to cancel any pending timers
    def cleanup(obj):
        key = getattr(obj, 'view', obj).id() if hasattr(obj, 'view') else id(obj)
        if key in timers and timers[key]:
            timers[key].cancel()
            del timers[key]
    
    # Attach the cleanup method to the wrapped function
    wrapped_func.cleanup = cleanup
    
    return wrapped_func


class CommentDecorationManager:
    """Manages the decoration of comments in a view."""
    
    def __init__(self, view):
        """Initialize with a Sublime Text view.
        
        Args:
            view: The Sublime Text view to decorate
        """
        self.view = view
        self._last_change_count = 0
        self._last_region_row = -1  # Track the row of the last highlighted region
        
    def should_process_view(self):
        """Check if the view needs to be processed based on syntax settings.
        
        Returns:
            bool: False if syntax is in disabled list, True otherwise
        """
        return self.view.settings().get("syntax") not in settings.disabled_syntax
        
    def needs_update(self):
        """Check if view has changed since last processing.
        
        Returns:
            bool: True if view has changed, False otherwise
        """
        current_change = self.view.change_count()
        if current_change != self._last_change_count:
            self._last_change_count = current_change
            return True
        return False
        
    def find_comment_regions(self):
        """Find all comment regions in the view.
        
        Returns:
            List of region objects representing comments
        """
        return self.view.find_by_selector(comment_selector)
        
    def is_adjacent_to_last_region(self, region):
        """Check if the current region is directly after the last highlighted region.
        
        Args:
            region: The current region to check
            
        Returns:
            bool: True if the region is on the line immediately following the last highlighted region
        """
        if self._last_region_row == -1:
            return False
            
        # Get row for the start of this region
        current_row, _ = self.view.rowcol(region.begin())
        
        # Check if this is the line immediately following the last highlighted line
        return current_row == self._last_region_row + 1
    
    def process_comment_line(self, line, to_decorate, reg, prev_match):
        """Process a single comment line and identify its tag.
        
        Args:
            line: The line text to process
            to_decorate: Dictionary to populate with regions
            reg: The region representing this line
            prev_match: The previous matched tag identifier
            
        Returns:
            str: The matched tag identifier or empty string
        """
        # Skip empty lines
        stripped_line = line.strip()
        if not stripped_line:
            return ""
            
        if not settings.get_matching_pattern().startswith(" "):
            line = stripped_line
        
        is_adjacent = self.is_adjacent_to_last_region(reg)
        
        # Try to match a tag pattern first
        for identifier in settings.tag_regex:
            if settings.get_regex(identifier).search(line.strip()):
                # Found a direct match
                to_decorate.setdefault(identifier, []).append(reg)
                # Update the last region row
                self._last_region_row, _ = self.view.rowcol(reg.end())
                return identifier
                
        # No direct match, check for continuation
        if prev_match and is_adjacent and (
            # Standard continuation with pattern matching
            (settings.continued_matching and line.startswith(settings.get_matching_pattern())) or
            # Auto-continue highlighting without requiring pattern match
            settings.auto_continue_highlight
        ):
            to_decorate.setdefault(prev_match, []).append(reg)
            # Update the last region row
            self._last_region_row, _ = self.view.rowcol(reg.end())
            return prev_match
            
        # No match found
        return ""
    
    @debounce    
    def apply_decorations(self):
        """Find and apply decorations to comments in the view."""
        if not self.should_process_view():
            return
            
        if not self.needs_update():
            return
            
        self.clear_decorations()  # Clear existing decorations first
        
        to_decorate = {}
        prev_match = ""
        self._last_region_row = -1  # Reset tracking for this run
        
        for region in self.find_comment_regions():
            for reg in self.view.split_by_newlines(region):
                line = self.view.substr(reg)
                result = self.process_comment_line(line, to_decorate, reg, prev_match)
                prev_match = result if result else prev_match  # Keep prev_match even if current line has no match

        # Apply the decorations
        self.apply_region_styles(to_decorate)
        
    def apply_region_styles(self, to_decorate):
        """Apply styles to the specified regions.
        
        Args:
            to_decorate: Dictionary mapping tag identifiers to regions
        """
        for key in to_decorate:
            tag = settings.tags.get(key)
            self.view.add_regions(
                key=key.lower(),
                regions=to_decorate.get(key),
                scope=settings.get_scope_for_region(key, tag),
                icon=settings.get_icon(),
                flags=settings.get_flags(tag),
            )
            
    def clear_decorations(self):
        """Remove all comment decorations from the view."""
        for region_key in settings.region_keys:
            self.view.erase_regions(region_key)
            
    def cleanup(self):
        """Clean up resources when manager is no longer needed."""
        # Call the cleanup method attached to the debounced function
        self.apply_decorations.cleanup(self)


class ColoredCommentsEditSchemeCommand(sublime_plugin.WindowCommand):
    """Command to edit the color scheme for Colored Comments."""

    def run(self):
        view = self.window.active_view()
        if not view:
            return

        scheme_path = self.get_scheme_path(view, 'color_scheme')
        if scheme_path != 'auto':
            self.open_scheme(scheme_path)
        else:
            paths = [
                (setting, self.get_scheme_path(view, setting))
                for setting in ('dark_color_scheme', 'light_color_scheme')
            ]
            choices = [
                sublime.QuickPanelItem(
                    setting, details=str(path), kind=KIND_SCHEME)
                for setting, path in paths
            ]

            def on_done(i):
                if i >= 0:
                    self.open_scheme(paths[i][1])

            self.window.show_quick_panel(choices, on_done)

    @staticmethod
    def get_scheme_path(view, setting_name):
        """Get the path to the color scheme file.
        
        Args:
            view: The view to get settings from
            setting_name: The name of the setting to retrieve
            
        Returns:
            ResourcePath or 'auto'
        """
        scheme_setting = view.settings().get(setting_name, DEFAULT_CS)
        if scheme_setting == 'auto':
            return 'auto'
        elif "/" not in scheme_setting:
            return ResourcePath.glob_resources(scheme_setting)[0]
        else:
            return ResourcePath(scheme_setting)

    def open_scheme(self, scheme_path):
        """Open the color scheme file for editing.
        
        Args:
            scheme_path: Path to the scheme to edit
        """
        self.window.run_command(
            'edit_settings',
            {
                'base_file': '/'.join(("${packages}",) + scheme_path.parts[1:]),
                'user_file': "${packages}/User/" + scheme_path.stem + '.sublime-color-scheme',
                'default': SCHEME_TEMPLATE,
            },
        )


class ColoredCommentsEventListener(sublime_plugin.EventListener):
    """Event listener for triggering comment decoration."""
    
    def __init__(self):
        """Initialize event listener with dictionary to track views."""
        self.managers = {}
    
    def get_manager(self, view):
        """Get or create a decoration manager for a view.
        
        Args:
            view: The view to get a manager for
            
        Returns:
            CommentDecorationManager: The manager for the view
        """
        view_id = view.id()
        if view_id not in self.managers:
            self.managers[view_id] = CommentDecorationManager(view)
        return self.managers[view_id]
    
    def on_init(self, views):
        """Handle view initialization.
        
        Args:
            views: List of views being initialized
        """
        for view in views:
            if view.window() is not None:
                manager = self.get_manager(view)
                manager.apply_decorations()  # Apply immediately on init

    def on_load_async(self, view):
        """Handle view loading.
        
        Args:
            view: The view being loaded
        """
        if view.window() is not None:
            manager = self.get_manager(view)
            manager.apply_decorations()  # Apply with debounce

    def on_modified_async(self, view):
        """Handle view modifications.
        
        Args:
            view: The view being modified
        """
        if view.window() is not None:
            manager = self.get_manager(view)
            manager.apply_decorations()  # Apply with debounce
            
    def on_close(self, view):
        """Clean up when a view is closed.
        
        Args:
            view: The view being closed
        """
        view_id = view.id()
        if view_id in self.managers:
            self.managers[view_id].cleanup()  # Clean up resources
            del self.managers[view_id]


class ColoredCommentsCommand(sublime_plugin.WindowCommand):
    """Command to apply comment decorations."""
    
    def run(self, vid=None):
        view = self.window.active_view() if vid is None else sublime.View(vid)
        decorator = CommentDecorationManager(view)
        decorator.apply_decorations()


class ColoredCommentsClearCommand(sublime_plugin.WindowCommand):
    """Command to clear comment decorations."""
    
    def run(self, vid=None):
        view = self.window.active_view() if vid is None else sublime.View(vid)
        decorator = CommentDecorationManager(view)
        decorator.clear_decorations()


def plugin_loaded() -> None:
    """Initialize plugin settings when loaded."""
    load_settings()
    log.set_debug_logging(settings.debug)


def plugin_unloaded() -> None:
    """Clean up when plugin is unloaded."""
    unload_settings()
