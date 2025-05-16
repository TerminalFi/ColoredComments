import sublime
import sublime_plugin
import time
import threading
import functools
import os
import re

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
        
    def is_adjacent_to_region(self, current_region, prev_region, view):
        """Check if the current region is directly after the previous region.
        
        Args:
            current_region: The current region to check
            prev_region: The previous region to check against
            view: The view containing the regions
            
        Returns:
            bool: True if the regions are on adjacent lines
        """
        current_row, _ = view.rowcol(current_region.begin())
        prev_row, _ = view.rowcol(prev_region.begin())
        
        # Check if this is the line immediately following the last highlighted line
        return current_row == prev_row + 1
    
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
        
        # Check if this is adjacent to the last highlighted line
        is_adjacent = False
        if self._last_region_row != -1:
            current_row, _ = self.view.rowcol(reg.begin())
            is_adjacent = current_row == self._last_region_row + 1
        
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


class ColoredCommentsListTagsCommand(sublime_plugin.WindowCommand):
    """Command to list all colored comment tags found in the project.

    This command finds and displays all colored comment tags in an output panel,
    showing their context, filename, and location.
    """

    def run(self, tag_filter=None, current_file_only=False):
        """Run the command to list all tags.

        Args:
            tag_filter: Optional filter to show only specific tags (e.g., "TODO")
            current_file_only: If True, only scan the current file
        """
        self.window.status_message("Searching for colored comments...")
        self.tag_filter = tag_filter
        self.current_file_only = current_file_only

        # Run the search in a separate thread to avoid UI blocking
        threading.Thread(target=self._find_tags).start()

    def is_adjacent_to_region(self, current_region, prev_region, view):
        """Check if the current region is directly after the previous region.
        
        Args:
            current_region: The current region to check
            prev_region: The previous region to check against
            view: The view containing the regions
            
        Returns:
            bool: True if the regions are on adjacent lines
        """
        current_row, _ = view.rowcol(current_region.begin())
        prev_row, _ = view.rowcol(prev_region.begin())
        
        # Check if this is the line immediately following the last highlighted line
        return current_row == prev_row + 1

    def _find_tags(self):
        """Find all tags in the project files by applying decorations to temporary views."""
        results = []
        files_to_scan = self._get_files_to_scan()
        processed_count = 0
        total_files = len(files_to_scan)

        # Update status periodically
        def update_status():
            self.window.status_message(f"Searching for colored comments... ({processed_count}/{total_files})")

        # Process each file
        for file_path in files_to_scan:
            try:
                # Update status every 10 files
                processed_count += 1
                if processed_count % 10 == 0:
                    sublime.set_timeout(update_status, 0)

                # Load file content
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Create a temporary view with the file content
                temp_view = self.window.create_output_panel('_colored_comments_temp_view')
                temp_view.run_command('append', {'characters': content})

                # Set the proper syntax
                self._set_view_syntax(temp_view, file_path)

                # Create a decoration manager for this view
                decorator = CommentDecorationManager(temp_view)

                # Apply the decorations (without debounce)
                self._apply_decorations_direct(decorator)

                # Extract the decorated regions
                file_results = self._extract_tag_regions(temp_view, file_path)
                results.extend(file_results)

                # Close the temporary view
                self.window.destroy_output_panel('_colored_comments_temp_view')

            except Exception as e:
                log.debug(f"Error processing {file_path}: {str(e)}")

        # Sort results by tag type then filename
        results.sort(key=lambda x: (x['tag'], x['file'], x['line']))

        # Update UI in main thread
        sublime.set_timeout(lambda: self._show_results(results), 0)

    def _get_files_to_scan(self):
        """Get a list of files to scan based on settings.

        Returns:
            list: List of file paths to scan
        """
        files_to_scan = []

        # If current file only, just return the active file
        if self.current_file_only:
            active_view = self.window.active_view()
            if active_view and active_view.file_name():
                return [active_view.file_name()]
            else:
                return []

        # Otherwise scan all files in project
        folders = self.window.folders()

        # If no project folders, use the directory of the active file
        if not folders and self.window.active_view():
            file_name = self.window.active_view().file_name()
            if file_name:
                folders = [os.path.dirname(file_name)]

        # If still no folders, can't proceed
        if not folders:
            return []

        # Walk the directory tree to collect files
        for folder in folders:
            for root, _, files in os.walk(folder):
                for file in files:
                    # Skip binary files, hidden files, and files we usually don't want to search
                    if self._should_skip_file(file):
                        continue

                    file_path = os.path.join(root, file)
                    files_to_scan.append(file_path)

        return files_to_scan

    def _should_skip_file(self, file_name):
        """Check if a file should be skipped during search.

        Args:
            file_name: The name of the file to check

        Returns:
            bool: True if the file should be skipped, False otherwise
        """
        # Skip hidden files
        if file_name.startswith('.'):
            return True

        # Skip common binary files and non-text files
        exclude_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.pdf',
            '.zip', '.tar', '.gz', '.rar', '.7z',
            '.pyc', '.pyo', '.exe', '.dll', '.obj', '.o',
            '.a', '.lib', '.so', '.dylib', '.ncb', '.sdf', '.suo',
            '.pdb', '.idb', '.ds_store'
        ]

        return any(file_name.lower().endswith(ext) for ext in exclude_extensions)

    def _set_view_syntax(self, view, file_path):
        """Set the correct syntax for the view based on file path.

        Args:
            view: The view to set syntax for
            file_path: The path of the file
        """
        # Use Sublime's built-in syntax detection
        syntax = sublime.find_syntax_for_file(file_path)
        if syntax:
            view.assign_syntax(syntax.path)

    def _apply_decorations_direct(self, decorator):
        """Apply decorations directly without debouncing.

        Args:
            decorator: The CommentDecorationManager instance
        """
        # Ensure we're not in a disabled syntax
        if not decorator.should_process_view():
            return

        # Reset any existing decorations
        decorator.clear_decorations()

        # We need to force the original method to process the view regardless of change count
        # Save the original state
        last_change_count = decorator._last_change_count

        # Force processing by setting change count to 0
        decorator._last_change_count = 0

        # Enable extra verbose debugging for this call
        original_debug = settings.debug
        settings.debug = True
        log.debug("=== ENABLING EXTRA VERBOSE DEBUGGING FOR DECORATION PROCESSING ===")

        # Access the original method without going through the debounce wrapper
        original_method = decorator.apply_decorations.__wrapped__
        original_method(decorator)

        # Restore debug setting
        settings.debug = original_debug

        # Restore the original state
        decorator._last_change_count = last_change_count

        # Log all regions immediately after decoration
        view = decorator.view
        log.debug("=== REGION INSPECTION AFTER DECORATION ===")
        for region_key in settings.region_keys:
            regions = view.get_regions(region_key)
            log.debug(f"Tag '{region_key}' has {len(regions)} regions:")
            for i, region in enumerate(regions):
                row, col = view.rowcol(region.begin())
                content = view.substr(region).strip()
                log.debug(f"  Region {i}: Line {row+1}, Pos {region.begin()}-{region.end()}, Content: '{content[:30]}...' if len(content) > 30 else content")

                # Log the full text and character positions for this region
                if i > 0:
                    prev_region = regions[i-1]
                    gap = region.begin() - prev_region.end()
                    prev_row, _ = view.rowcol(prev_region.begin())
                    log.debug(f"    Gap from previous region: {gap} chars, {row-prev_row} lines")

                    # If gap is 1 char but more than 0 lines, something's wrong
                    if gap <= 1 and row > prev_row:
                        log.debug(f"    POTENTIAL ISSUE: Small char gap but line break detected")
                        # Dump the actual text between the regions
                        between_text = view.substr(sublime.Region(prev_region.end(), region.begin()))
                        log.debug(f"    Text between regions: '{repr(between_text)}'")

    def _extract_tag_regions(self, view, file_path):
        """Extract tagged regions from a view.

        Args:
            view: The view with decorations applied
            file_path: The path of the file

        Returns:
            list: List of tag data dictionaries
        """
        results = []
        relative_path = os.path.relpath(file_path, self.window.folders()[0]) if self.window.folders() else file_path

        log.debug(f"Extracting tag regions from {file_path}")

        # Debug view properties
        log.debug(f"View settings: syntax={view.settings().get('syntax')}")
        log.debug(f"Matching pattern: '{settings.get_matching_pattern()}'")
        log.debug(f"Auto-continue: {settings.auto_continue_highlight}")
        log.debug(f"Continued matching: {settings.continued_matching}")

        # Check if view has content
        content_size = view.size()
        log.debug(f"View content size: {content_size} chars")
        if content_size > 0:
            sample = view.substr(sublime.Region(0, min(100, content_size)))
            log.debug(f"Content sample: '{sample}'")

        # Process each tag type
        for region_key in settings.region_keys:
            # Skip if tag_filter is specified and doesn't match
            if self.tag_filter and region_key.lower() != self.tag_filter.lower():
                continue

            # Find the tag name from the region key
            tag_name = next((name for name in settings.tags.keys()
                           if name.lower() == region_key), region_key.upper())

            # Get all regions for this tag and sort by line number
            regions = view.get_regions(region_key)
            if not regions:
                log.debug(f"  No regions found for tag '{tag_name}'")
                continue

            # Sort regions by position
            regions.sort(key=lambda r: r.begin())
            log.debug(f"  Found {len(regions)} regions for tag '{tag_name}'")

            # Dump raw region data
            log.debug(f"  Raw regions: {regions}")

            # Process regions in order - group by original tag first
            current_regions = []

            # First, collect regions into groups
            for region in regions:
                row, col = view.rowcol(region.begin())
                content = view.substr(region).strip()

                # Check if this is the start of a new comment group
                is_new_group = True

                # If we have a current group, check if this is a continuation
                if current_regions:
                    prev_region = current_regions[-1]

                    # Check if regions are on adjacent lines
                    if self.is_adjacent_to_region(region, prev_region, view):
                        log.debug(f"  Found adjacent region at line {row+1}")
                        # Check if auto-continue is enabled
                        if settings.auto_continue_highlight:
                            log.debug(f"  Auto-continue is enabled, continuing group")
                            # Consider it a continuation
                            is_new_group = False
                        # Check if it starts with the continuation pattern
                        elif settings.continued_matching:
                            # For Python comments, need to handle the comment marker
                            # Look at actual content including comment marker
                            line_text = view.substr(view.line(region.begin()))
                            line_text = line_text.lstrip()  # Remove leading whitespace

                            log.debug(f"  Checking line text: '{line_text}'")

                            # Skip comment marker if present - remove Python and JavaScript/C-style comment markers
                            if line_text.startswith('#'):
                                line_text = line_text[1:].lstrip()
                            elif line_text.startswith('//'):
                                line_text = line_text[2:].lstrip()
                            elif line_text.startswith('/*'):
                                line_text = line_text[2:].lstrip()

                            log.debug(f"  After removing comment marker: '{line_text}'")

                            # Now check if it starts with the continuation pattern
                            if line_text.startswith(settings.get_matching_pattern()):
                                log.debug(f"  Found continuation pattern, continuing group")
                                # Consider it a continuation
                                is_new_group = False

                # If this is a new group, start a new collection
                if is_new_group:
                    log.debug(f"  Starting new region group at line {row+1}")
                    # If we have a previous group, process it
                    if current_regions:
                        self._add_tag_entry(view, current_regions, tag_name, relative_path, results)
                    # Start new group
                    current_regions = [region]
                else:
                    # Add to the current group
                    current_regions.append(region)

            # Process the last group if we have one
            if current_regions:
                self._add_tag_entry(view, current_regions, tag_name, relative_path, results)

        log.debug(f"Extracted {len(results)} total tag entries from {file_path}")
        return results

    def _add_tag_entry(self, view, regions, tag_name, relative_path, results):
        """Add a tag entry from a group of regions.

        Args:
            view: The Sublime Text view
            regions: List of regions for this tag group
            tag_name: The name of the tag
            relative_path: Relative path to the file
            results: Results list to append to
        """
        if not regions:
            return

        # Get info from the first region
        first_region = regions[0]
        row, col = view.rowcol(first_region.begin())

        # Collect all content
        content_lines = []
        for region in regions:
            line_content = view.substr(region).strip()

            # For continuation lines, we might want to strip the pattern
            if len(content_lines) > 0 and settings.continued_matching:
                # Get the raw line
                line_text = view.substr(view.line(region.begin()))
                line_text = line_text.lstrip()  # Remove leading whitespace

                # Skip comment marker if present
                if line_text.startswith('#'):
                    line_text = line_text[1:].lstrip()
                elif line_text.startswith('//'):
                    line_text = line_text[2:].lstrip()
                elif line_text.startswith('/*'):
                    line_text = line_text[2:].lstrip()

                # Remove continuation pattern if present
                pattern = settings.get_matching_pattern()
                if line_text.startswith(pattern):
                    # Remove pattern from the beginning
                    line_content = line_text[len(pattern):].strip()

            content_lines.append(line_content)

        # Add the tag entry
        results.append({
            'tag': tag_name,
            'file': relative_path,
            'line': row + 1,  # 1-based line number
            'column': col + 1,  # 1-based column
            'content': content_lines
        })

    def _show_results(self, results):
        """Show the search results in a quick panel.

        Args:
            results: List of tags found
        """
        if not results:
            self.window.status_message("No colored comments found")
            return

        # Create output panel
        panel = self.window.create_output_panel('colored_comments_tags')
        panel.set_read_only(False)
        panel.run_command('erase_view')

        # Group results by tag type for better organization
        tags_by_type = {}
        for item in results:
            tag_type = item['tag']
            if tag_type not in tags_by_type:
                tags_by_type[tag_type] = []
            tags_by_type[tag_type].append(item)

        # Format and insert results
        for tag_type in sorted(tags_by_type.keys()):
            # Add a header for each tag type
            panel.run_command('append', {'characters': f"\n=== {tag_type} ({len(tags_by_type[tag_type])}) ===\n\n"})

            for item in tags_by_type[tag_type]:
                # Format the header line with file, line, column
                header = f"{item['file']}:{item['line']}:{item['column']}"

                # Format the content lines with indentation
                if item['content']:
                    content = '\n    '.join(item['content'])
                    # Insert into panel
                    panel.run_command('append', {'characters': f"{header}\n    {content}\n\n"})
                else:
                    # In case of empty content, still show the file reference
                    panel.run_command('append', {'characters': f"{header}\n    (no content)\n\n"})

        panel.set_read_only(True)

        # Setup panel for navigation
        self._setup_navigation(panel)

        # Show the panel
        self.window.run_command('show_panel', {'panel': 'output.colored_comments_tags'})
        total_tags = sum(len(items) for items in tags_by_type.values())
        self.window.status_message(f"Found {total_tags} colored comments across {len(tags_by_type)} tag types")

    def _setup_navigation(self, panel):
        """Set up the panel for file navigation.

        Args:
            panel: The output panel to configure
        """
        # Set syntax for better readability
        panel.assign_syntax('Packages/Text/Plain text.tmLanguage')

        # Set up click handling for navigation
        settings = panel.settings()
        settings.set('result_file_regex', r'^(.+):(\d+):(\d+)')
        settings.set('result_base_dir', self.window.folders()[0] if self.window.folders() else '')

        # Enable line wrapping for readability
        settings.set('word_wrap', True)


class ColoredCommentsToggleDebugCommand(sublime_plugin.WindowCommand):
    """Command to toggle debug logging."""

    def run(self):
        """Toggle debug logging on/off."""
        # Toggle the debug setting
        new_debug_state = not settings.debug
        settings_obj = sublime.load_settings("colored_comments.sublime-settings")
        settings_obj.set("debug", new_debug_state)
        sublime.save_settings("colored_comments.sublime-settings")

        # Update the runtime setting
        settings.debug = new_debug_state
        log.set_debug_logging(settings.debug)

        # Show message
        state = "ON" if new_debug_state else "OFF"
        self.window.status_message(f"Colored Comments: Debug logging turned {state}")

        # If debug was turned on, show where to find logs
        if new_debug_state:
            # Show a quick panel with instructions
            self.window.show_quick_panel(
                ["Debug logging enabled",
                 "Check Sublime console for logs (View > Show Console)",
                 "Run the tag list command to see debug output"],
                lambda _: None,
                sublime.KEEP_OPEN_ON_FOCUS_LOST,
                0
            )


class ColoredCommentsShowLogsCommand(sublime_plugin.WindowCommand):
    """Command to show debug logs in a panel."""

    def run(self):
        """Display the debug logs in a panel."""
        from .plugin.logger import dump_logs_to_panel
        dump_logs_to_panel(self.window)


def plugin_loaded() -> None:
    """Initialize plugin settings when loaded."""
    load_settings()
    log.set_debug_logging(settings.debug)


def plugin_unloaded() -> None:
    """Clean up when plugin is unloaded."""
    unload_settings()
