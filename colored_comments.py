import sublime
import sublime_plugin
import asyncio
import os
import re
from pathlib import Path

import sublime_aio

from .plugin import logger as log
from .lib.sublime_lib import ResourcePath
from .plugin.settings import load_settings, settings, unload_settings
from .templates import SCHEME_TEMPLATE

NAME = "Colored Comments"
VERSION = "4.0.0"

comment_selector = "comment - punctuation.definition.comment"
KIND_SCHEME = (sublime.KIND_ID_VARIABLE, "s", "Scheme")
DEFAULT_CS = 'Packages/Color Scheme - Default/Mariana.sublime-color-scheme'


class CommentProcessor:
    """Unified comment processor for both decoration and tag scanning."""

    def __init__(self, view):
        self.view = view

    def should_process_view(self):
        """Check if the view needs to be processed based on syntax settings."""
        syntax = self.view.settings().get("syntax")
        should_process = syntax not in settings.disabled_syntax
        log.debug(f"View {self.view.id()} syntax check: {syntax}, should_process: {should_process}")
        return should_process

    def find_comment_regions(self):
        """Find all comment regions in the view."""
        regions = self.view.find_by_selector(comment_selector)
        log.debug(f"View {self.view.id()} found {len(regions)} comment regions using selector: {comment_selector}")
        return regions

    async def process_comments(self, processor_func, batch_size=100):
        """Process all comments in the view using the provided processor function.

        Args:
            processor_func: Function to call for each comment line
                           Should accept (line, reg, line_num, **kwargs)
            batch_size: Number of regions to process in each batch
        """
        if not self.should_process_view():
            log.debug(f"View {self.view.id()} should not be processed")
            return []

        comment_regions = self.find_comment_regions()

        if not comment_regions:
            log.debug(f"View {self.view.id()} no comment regions found")
            return []

        results = []
        total_processed = 0

        # Process in batches to maintain UI responsiveness
        for i in range(0, len(comment_regions), batch_size):
            batch = comment_regions[i:i + batch_size]
            log.debug(f"View {self.view.id()} processing batch {i//batch_size + 1}, regions {i} to {i + len(batch)}")

            batch_processed = 0
            for region in batch:
                for reg in self.view.split_by_newlines(region):
                    line = self.view.substr(reg)
                    line_num = self.view.rowcol(reg.begin())[0] + 1

                    result = await processor_func(line, reg, line_num)
                    if result is not None:
                        if isinstance(result, list):
                            results.extend(result)
                        else:
                            results.append(result)

                    batch_processed += 1

            total_processed += batch_processed
            log.debug(f"View {self.view.id()} batch complete, processed {batch_processed} lines, total: {total_processed}")

            # Yield control after each batch to keep UI responsive
            if i + batch_size < len(comment_regions):
                await asyncio.sleep(0.001)

        return results


class CommentDecorationManager:
    """Manages the decoration of comments in a view with async support."""

    def __init__(self, view):
        self.view = view
        self._last_change_count = 0
        self._last_region_row = -1
        self._processing = False
        self.processor = CommentProcessor(view)
        log.debug(f"CommentDecorationManager created for view {view.id()}: {view.file_name()}")

    def should_process_view(self):
        """Check if the view needs to be processed based on syntax settings."""
        return self.processor.should_process_view()

    def needs_update(self):
        """Check if view has changed since last processing."""
        current_change = self.view.change_count()
        needs_update = current_change != self._last_change_count
        if needs_update:
            log.debug(f"View {self.view.id()} needs update: change_count {self._last_change_count} -> {current_change}")
            self._last_change_count = current_change
        else:
            log.debug(f"View {self.view.id()} no update needed: change_count unchanged at {current_change}")
        return needs_update

    def find_comment_regions(self):
        """Find all comment regions in the view."""
        return self.processor.find_comment_regions()

    async def process_comment_line_for_decoration(self, line, reg, line_num, to_decorate, prev_match=""):
        """Process a single comment line for decoration."""
        stripped_line = line.strip()
        if not stripped_line:
            return None

        if not settings.get_matching_pattern().startswith(" "):
            line = stripped_line

        # Check adjacency for continuation
        is_adjacent = False
        if self._last_region_row != -1:
            current_row = line_num - 1  # line_num is 1-based, rowcol is 0-based
            is_adjacent = current_row == self._last_region_row + 1

        # Try to match tag patterns first
        for identifier in settings.tag_regex:
            if settings.get_regex(identifier).search(line.strip()):
                to_decorate.setdefault(identifier, []).append(reg)
                self._last_region_row = line_num - 1
                log.debug(f"View {self.view.id()} matched tag '{identifier}' at line: {stripped_line[:50]}...")
                return identifier

        # Check for continuation
        if prev_match and is_adjacent and (
            (settings.continued_matching and line.startswith(settings.get_matching_pattern())) or
            settings.auto_continue_highlight
        ):
            to_decorate.setdefault(prev_match, []).append(reg)
            self._last_region_row = line_num - 1
            log.debug(f"View {self.view.id()} continued tag '{prev_match}' at line: {stripped_line[:50]}...")
            return prev_match

        return None

    def apply_region_styles(self, to_decorate):
        """Apply visual styles to decorated regions."""
        total_regions = sum(len(regions) for regions in to_decorate.values())
        log.debug(f"View {self.view.id()} applying styles to {total_regions} regions across {len(to_decorate)} tag types")

        for identifier, regions in to_decorate.items():
            if identifier in settings.tags:
                tag = settings.tags[identifier]
                scope = settings.get_scope_for_region(identifier, tag)
                flags = settings.get_flags(tag)
                icon = settings.get_icon()

                log.debug(f"View {self.view.id()} applying {len(regions)} regions for tag '{identifier}' with scope '{scope}'")

                self.view.add_regions(
                    identifier.lower(),
                    regions,
                    scope,
                    icon=icon,
                    flags=flags
                )

    def clear_decorations(self):
        """Clear all existing decorations from the view."""
        log.debug(f"View {self.view.id()} clearing decorations for keys: {settings.region_keys}")
        for key in settings.region_keys:
            self.view.erase_regions(key)

    def cleanup(self):
        """Clean up resources when the manager is no longer needed."""
        log.debug(f"CommentDecorationManager cleanup for view {self.view.id()}")
        self.clear_decorations()

    async def apply_decorations(self):
        """Apply decorations asynchronously with batching."""
        log.debug(f"View {self.view.id()} apply_decorations called, processing: {self._processing}")

        if self._processing:
            log.debug(f"View {self.view.id()} already processing, skipping")
            return

        if not self.should_process_view():
            log.debug(f"View {self.view.id()} should not be processed, skipping")
            return

        self._processing = True
        log.debug(f"View {self.view.id()} starting decoration process")

        try:
            # For initial load, always process even if change count is same
            needs_update = self.needs_update()
            has_existing_decorations = any(len(self.view.get_regions(key)) > 0 for key in settings.region_keys)

            if not needs_update and has_existing_decorations:
                log.debug(f"View {self.view.id()} no update needed and has existing decorations")
                return

            if not needs_update:
                log.debug(f"View {self.view.id()} no change detected but no existing decorations, forcing update")

            log.debug(f"View {self.view.id()} clearing existing decorations")
            self.clear_decorations()

            to_decorate = {}
            prev_match = ""
            self._last_region_row = -1

            # Use the unified comment processor
            async def decoration_processor(line, reg, line_num):
                nonlocal prev_match
                result = await self.process_comment_line_for_decoration(
                    line, reg, line_num, to_decorate, prev_match
                )
                prev_match = result if result else prev_match
                return None  # We don't need to collect results, just populate to_decorate

            await self.processor.process_comments(decoration_processor, batch_size=100)

            log.debug(f"View {self.view.id()} applying region styles")
            self.apply_region_styles(to_decorate)
            log.debug(f"View {self.view.id()} decoration process complete")

        except Exception as e:
            log.debug(f"Error in apply_decorations for view {self.view.id()}: {e}")
            import traceback
            log.debug(f"Traceback: {traceback.format_exc()}")
        finally:
            self._processing = False
            log.debug(f"View {self.view.id()} decoration process finished, processing flag reset")


class ColoredCommentsEditSchemeCommand(sublime_plugin.WindowCommand):
    """Command to edit the color scheme for colored comments."""

    def run(self):
        log.debug("ColoredCommentsEditSchemeCommand.run() called")
        view = self.window.active_view()
        current_scheme = self.get_scheme_path(view, "color_scheme")

        if not current_scheme:
            current_scheme = DEFAULT_CS

        scheme_list = [
            [
                'Edit Current: ' + current_scheme.split('/')[-1],
                current_scheme,
                current_scheme
            ]
        ]

        resources = sublime.find_resources("*.sublime-color-scheme")
        resources.extend(sublime.find_resources("*.tmTheme"))

        for resource in resources:
            scheme_list.append([
                resource.split('/')[-1],
                resource,
                resource
            ])

        def on_done(i):
            if i >= 0:
                log.debug(f"Opening scheme: {scheme_list[i][2]}")
                self.open_scheme(scheme_list[i][2])

        self.window.show_quick_panel(scheme_list, on_done)

    @staticmethod
    def get_scheme_path(view, setting_name):
        scheme = None
        if view:
            scheme = view.settings().get(setting_name)
        if not scheme:
            scheme = sublime.load_settings("Preferences.sublime-settings").get(setting_name)
        if scheme and not scheme.startswith('Packages/'):
            if scheme.find('/') != -1:
                scheme = '/'.join(['Packages'] + scheme.split('/')[1:])
        return scheme

    def open_scheme(self, scheme_path):
        try:
            resource = ResourcePath.from_file_path(scheme_path)
            new_view = self.window.open_file(str(resource))

            def check_loaded():
                if new_view.is_loading():
                    sublime.set_timeout(check_loaded, 50)
                else:
                    self.inject_scheme_template(new_view)

            check_loaded()
        except Exception as e:
            log.debug(f"Error opening scheme: {e}")

    def inject_scheme_template(self, view):
        content = view.substr(sublime.Region(0, view.size()))
        if "comments.important" not in content:
            insertion_point = view.size()
            if content.strip().endswith('}'):
                lines = content.split('\n')
                for i in range(len(lines) - 1, -1, -1):
                    if '}' in lines[i]:
                        insertion_point = sum(len(line) + 1 for line in lines[:i])
                        break

            view.run_command('insert', {
                'characters': '\n' + SCHEME_TEMPLATE.rstrip() + '\n'
            })


class ColoredCommentsEventListener(sublime_aio.ViewEventListener):
    """Async event listener using sublime_aio for optimal performance."""

    def __init__(self, view):
        super().__init__(view)
        self.manager = CommentDecorationManager(view)
        log.debug(f"ColoredCommentsEventListener created for view {view.id()}: {view.file_name()}")

    @sublime_aio.debounced(settings.debounce_delay)
    async def on_modified(self):
        """Handle view modifications without debouncing (for testing)."""
        log.debug(f"*** ON_MODIFIED EVENT FIRED for view {self.view.id()} ***")
        log.debug(f"ColoredCommentsEventListener.on_modified() called for view {self.view.id()}")

        if self.view.settings().get("syntax") in settings.disabled_syntax:
            log.debug(f"View {self.view.id()} syntax disabled, skipping")
            return

        log.debug(f"View {self.view.id()} triggering decoration update from on_modified")
        await self.manager.apply_decorations()

    async def on_load(self):
        """Handle view loading."""
        log.debug(f"*** ON_LOAD EVENT FIRED for view {self.view.id()} ***")
        log.debug(f"ColoredCommentsEventListener.on_load() called for view {self.view.id()}: {self.view.file_name()}")

        if self.view.settings().get("syntax") in settings.disabled_syntax:
            log.debug(f"View {self.view.id()} syntax disabled, skipping")
            return

        log.debug(f"View {self.view.id()} triggering decoration on load")
        await self.manager.apply_decorations()

    async def on_activated(self):
        """Handle view activation."""
        log.debug(f"*** ON_ACTIVATED EVENT FIRED for view {self.view.id()} ***")
        log.debug(f"ColoredCommentsEventListener.on_activated() called for view {self.view.id()}: {self.view.file_name()}")

        if self.view.settings().get("syntax") in settings.disabled_syntax:
            log.debug(f"View {self.view.id()} syntax disabled, skipping")
            return

        log.debug(f"View {self.view.id()} triggering decoration on activation")
        await self.manager.apply_decorations()

    def on_close(self):
        """Handle view closing - synchronous cleanup."""
        log.debug(f"ColoredCommentsEventListener.on_close() called for view {self.view.id()}")
        self.manager.cleanup()


class ColoredCommentsCommand(sublime_aio.ViewCommand):
    """Command to manually trigger comment decoration."""

    async def run(self):
        """Apply comment decorations to the current view."""
        log.debug(f"ColoredCommentsCommand.run() called for view {self.view.id()}")
        manager = CommentDecorationManager(self.view)

        if not manager.should_process_view():
            log.debug(f"View {self.view.id()} type not supported for colored comments")
            sublime.status_message("View type not supported for colored comments")
            return

        # Force an update by resetting the change count
        manager._last_change_count = 0
        log.debug(f"View {self.view.id()} forcing decoration update")
        await manager.apply_decorations()
        sublime.status_message("Comment decorations applied")


class ColoredCommentsClearCommand(sublime_plugin.TextCommand):
    """Command to clear all comment decorations."""

    def run(self, edit):
        log.debug(f"ColoredCommentsClearCommand.run() called for view {self.view.id()}")
        view = self.view
        manager = CommentDecorationManager(view)
        manager.clear_decorations()
        sublime.status_message("Comment decorations cleared")


class AsyncTagScanner:
    """Async tag scanner for efficient project-wide scanning."""

    def __init__(self, window):
        self.window = window
        log.debug(f"AsyncTagScanner created for window {window.id()}")

    async def scan_for_tags(self, tag_filter=None, current_file_only=False):
        """Scan for tags in project files asynchronously."""
        log.debug(f"AsyncTagScanner.scan_for_tags() called, tag_filter: {tag_filter}, current_file_only: {current_file_only}")
        results = []
        files = await self._get_files_to_scan(current_file_only)

        if not files:
            log.debug("No files to scan")
            return results

        total_files = len(files)
        log.debug(f"Scanning {total_files} files for tags")

        # Process files in batches for better progress reporting
        batch_size = 10
        for i in range(0, total_files, batch_size):
            batch = files[i:i + batch_size]
            log.debug(f"Processing batch {i//batch_size + 1}, files {i} to {i + len(batch)}")

            # Process batch concurrently
            batch_tasks = [
                self._scan_file(file_path, tag_filter)
                for file_path in batch
            ]

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Collect results, filtering out exceptions
            batch_found = 0
            for result in batch_results:
                if isinstance(result, list):
                    results.extend(result)
                    batch_found += len(result)
                elif isinstance(result, Exception):
                    log.debug(f"Error in batch processing: {result}")

            log.debug(f"Batch complete, found {batch_found} tags in this batch")

            # Update progress
            progress = min(100, int(((i + batch_size) / total_files) * 100))
            sublime.status_message(f"Scanning tags... {progress}% ({len(results)} found)")

            # Yield control to keep UI responsive
            await asyncio.sleep(0.01)

        log.debug(f"Tag scanning complete, found {len(results)} total tags")
        return results

    async def _get_files_to_scan(self, current_file_only):
        """Get list of files to scan asynchronously."""
        if current_file_only:
            view = self.window.active_view()
            if view and view.file_name():
                log.debug(f"Scanning current file only: {view.file_name()}")
                return [Path(view.file_name())]
            log.debug("No current file to scan")
            return []

        files = []
        folders = self.window.folders()

        if not folders:
            log.debug("No project folders found")
            return files

        log.debug(f"Scanning {len(folders)} project folders")

        # Collect files from all project folders
        for folder in folders:
            folder_path = Path(folder)
            log.debug(f"Scanning folder: {folder_path}")
            try:
                folder_files = await self._scan_directory(folder_path)
                files.extend(folder_files)
                log.debug(f"Found {len(folder_files)} files in {folder_path}")
            except Exception as e:
                log.debug(f"Error scanning folder {folder_path}: {e}")

        log.debug(f"Total files to scan: {len(files)}")
        return files

    async def _scan_directory(self, directory):
        """Scan directory for relevant files asynchronously."""
        files = []
        try:
            # Use rglob for recursive scanning
            all_files = list(directory.rglob('*'))
            log.debug(f"Directory {directory} contains {len(all_files)} total items")

            # Filter files in batches to avoid blocking
            batch_size = 500
            for i in range(0, len(all_files), batch_size):
                batch = all_files[i:i + batch_size]

                batch_files = 0
                for file_path in batch:
                    if (file_path.is_file() and
                        not self._should_skip_file(file_path) and
                        self._is_text_file(file_path)):
                        files.append(file_path)
                        batch_files += 1

                log.debug(f"Directory batch {i//batch_size + 1}: {batch_files} valid files found")

                # Yield control periodically
                if i + batch_size < len(all_files):
                    await asyncio.sleep(0.001)

        except (OSError, PermissionError) as e:
            log.debug(f"Error accessing directory {directory}: {e}")

        return files

    async def _scan_file(self, file_path, tag_filter):
        """Scan a single file for comment tags using the unified CommentProcessor."""
        results = []
        file_view = None
        was_already_open = False

        try:
            log.debug(f"Scanning file {file_path} for tags")

            # Check if file is already open in any view
            for view in self.window.views():
                if view.file_name() == str(file_path):
                    file_view = view
                    was_already_open = True
                    log.debug(f"File {file_path.name} is already open, using existing view")
                    break

            # If not already open, open it as transient
            if not file_view:
                log.debug(f"Opening file {file_path.name} as transient view")
                file_view = self.window.open_file(str(file_path), sublime.ENCODED_POSITION | sublime.TRANSIENT)
                was_already_open = False

            # Wait for the file to load
            while file_view.is_loading():
                await asyncio.sleep(0.01)

            log.debug(f"File {file_path.name} loaded, using CommentProcessor")

            # Use the unified CommentProcessor
            processor = CommentProcessor(file_view)

            # Create a processor function for tag scanning
            async def tag_processor(line, reg, line_num):
                return await self._process_comment_line(line, line_num, file_path, tag_filter)

            # Process comments using the unified processor
            file_results = await processor.process_comments(tag_processor, batch_size=50)
            results.extend(file_results)

            if len(file_results) > 0:
                log.debug(f"File {file_path.name} contains {len(file_results)} tags total")
            else:
                log.debug(f"File {file_path.name} contains no matching tags")

        except Exception as e:
            log.debug(f"Error scanning file {file_path}: {e}")
            import traceback
            log.debug(f"Traceback: {traceback.format_exc()}")
        finally:
            # Only close the view if we opened it as transient AND it's not the active view
            if file_view and not was_already_open and file_view.is_valid():
                active_view = self.window.active_view()
                if file_view != active_view:
                    log.debug(f"Closing transient view for {file_path.name}")
                    file_view.close()
                else:
                    log.debug(f"Not closing {file_path.name} because it's the active view")

        return results

    async def _process_comment_line(self, line, line_num, file_path, tag_filter):
        """Process a single comment line for tag matches (unified with CommentDecorationManager logic)."""
        stripped_line = line.strip()
        if not stripped_line:
            return None

        # Use the same matching pattern logic as CommentDecorationManager
        if not settings.get_matching_pattern().startswith(" "):
            line = stripped_line

        results = []
        for tag_name, regex in settings.tag_regex.items():
            # Apply tag filter if specified
            if tag_filter and tag_name.lower() != tag_filter.lower():
                continue

            # Use the same regex matching as CommentDecorationManager
            if regex.search(line.strip()):
                # Calculate relative path for display
                try:
                    if self.window.folders():
                        relative_path = str(file_path.relative_to(Path(self.window.folders()[0])))
                    else:
                        relative_path = file_path.name
                except ValueError:
                    relative_path = file_path.name

                results.append({
                    'tag': tag_name,
                    'line': stripped_line,
                    'line_num': line_num,
                    'file': str(file_path),
                    'relative_path': relative_path
                })
                log.debug(f"Found {tag_name} tag in {file_path.name}:{line_num}: {stripped_line[:50]}...")

        return results if results else None

    def _should_skip_file(self, file_path):
        """Check if file should be skipped based on extension and path."""
        # Skip binary file extensions
        skip_extensions = {
            '.pyc', '.pyo', '.class', '.o', '.obj', '.exe', '.dll', '.so', '.dylib',
            '.jar', '.war', '.ear', '.zip', '.tar', '.gz', '.bz2', '.7z',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
        }

        # Skip certain directories
        skip_dirs = {
            '__pycache__', '.git', '.svn', '.hg', 'node_modules',
            '.vscode', '.idea', '.vs', 'bin', 'obj', 'build', 'dist'
        }

        # Check extension
        if file_path.suffix.lower() in skip_extensions:
            return True

        # Check if any part of the path contains skip directories
        for part in file_path.parts:
            if part in skip_dirs:
                return True

        return False

    def _is_text_file(self, file_path):
        """Check if file is likely a text file."""
        # Known text file extensions
        text_extensions = {
            '.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml',
            '.md', '.rst', '.c', '.cpp', '.h', '.hpp', '.java', '.cs', '.php',
            '.rb', '.go', '.rs', '.swift', '.kt', '.scala', '.sh', '.bat',
            '.sql', '.r', '.m', '.pl', '.lua', '.vim', '.el', '.clj', '.hs'
        }

        if file_path.suffix.lower() in text_extensions:
            return True

        # For files without extension, try to detect if they're text
        if not file_path.suffix:
            try:
                with open(file_path, 'rb') as f:
                    chunk = f.read(512)
                    # Simple heuristic: if it contains mostly printable ASCII, it's probably text
                    text_chars = sum(1 for byte in chunk if 32 <= byte <= 126 or byte in (9, 10, 13))
                    return text_chars / len(chunk) > 0.7 if chunk else False
            except:
                return False

        return False


class ColoredCommentsListTagsCommand(sublime_aio.WindowCommand):
    """Async command to list all comment tags in the project."""

    async def run(self, tag_filter=None, current_file_only=False):
        """Run the tag listing command asynchronously."""
        log.debug(f"ColoredCommentsListTagsCommand.run() called, tag_filter: {tag_filter}, current_file_only: {current_file_only}")

        # Validate tag_filter if provided
        if tag_filter and tag_filter not in settings.tag_regex:
            available_tags = ", ".join(settings.tag_regex.keys())
            sublime.error_message(
                f"Unknown tag filter: '{tag_filter}'\n\n"
                f"Available tags: {available_tags}"
            )
            return

        scanner = AsyncTagScanner(self.window)

        try:
            sublime.status_message("Scanning for comment tags...")
            results = await scanner.scan_for_tags(tag_filter, current_file_only)

            if results:
                log.debug(f"Found {len(results)} tag results")
                self._show_results(results, tag_filter, current_file_only)
                scope_text = "current file" if current_file_only else "project"
                filter_text = f" (filtered by '{tag_filter}')" if tag_filter else ""
                sublime.status_message(f"Found {len(results)} comment tags in {scope_text}{filter_text}")
            else:
                log.debug("No comment tags found")
                scope_text = "current file" if current_file_only else "project"
                filter_text = f" matching '{tag_filter}'" if tag_filter else ""
                sublime.status_message(f"No comment tags found in {scope_text}{filter_text}")

                # Show more helpful message
                if tag_filter:
                    sublime.message_dialog(f"No '{tag_filter}' tags found in {scope_text}.")
                else:
                    available_tags = ", ".join(settings.tag_regex.keys())
                    sublime.message_dialog(
                        f"No comment tags found in {scope_text}.\n\n"
                        f"Available tag types: {available_tags}\n\n"
                        f"Example usage in comments:\n"
                        f"# TODO: Fix this issue\n"
                        f"# FIXME: This needs work\n"
                        f"# ! Important note"
                    )

        except Exception as e:
            log.debug(f"Error in tag scanning: {e}")
            import traceback
            log.debug(f"Traceback: {traceback.format_exc()}")
            sublime.error_message(f"Error scanning for tags: {str(e)}")

    def _show_results(self, results, tag_filter=None, current_file_only=False):
        """Show results in a quick panel with navigation and live preview."""
        # Sort results by tag type, then by file, then by line number
        results.sort(key=lambda x: (x['tag'], x['relative_path'], x['line_num']))
        
        # Store original viewport positions for all open views
        original_positions = {}
        for view in self.window.views():
            if view.file_name():
                original_positions[view.file_name()] = {
                    'viewport_position': view.viewport_position(),
                    'selection': [r for r in view.sel()],
                    'view_id': view.id()
                }
        
        panel_items = []
        for result in results:
            # Truncate long lines for better display
            tag_line = result['line'].strip()
            if len(tag_line) > 80:
                tag_line = tag_line[:77] + "..."
                
            # Format the display
            tag_display = f"[{result['tag']}]"
            line_display = tag_line
            location_display = f"{result['relative_path']}:{result['line_num']}"
            
            panel_items.append([
                f"{tag_display} {line_display}",
                location_display
            ])

        # Add header information
        scope_text = "Current File" if current_file_only else "Project"
        filter_text = f" - {tag_filter} Tags" if tag_filter else " - All Tags"
        header_text = f"{scope_text}{filter_text} ({len(results)} found)"

        def restore_original_positions():
            """Restore all views to their original positions."""
            for file_path, pos_data in original_positions.items():
                # Find the view for this file
                for view in self.window.views():
                    if view.file_name() == file_path and view.id() == pos_data['view_id']:
                        # Restore viewport position
                        view.set_viewport_position(pos_data['viewport_position'], False)
                        # Restore selection
                        view.sel().clear()
                        for region in pos_data['selection']:
                            view.sel().add(region)
                        break

        def on_done(index):
            if index >= 0:
                result = results[index]
                log.debug(f"Opening file at {result['file']}:{result['line_num']}")
                # Open file at specific line (this will be the final navigation)
                self.window.open_file(
                    f"{result['file']}:{result['line_num']}",
                    sublime.ENCODED_POSITION
                )
            else:
                # User cancelled, restore original positions
                log.debug("Tag list cancelled, restoring original viewport positions")
                restore_original_positions()

        def on_highlight(index):
            if index >= 0:
                result = results[index]
                
                # Show preview in status bar
                preview_line = result['line'].strip()[:100]
                sublime.status_message(f"[{result['tag']}] {preview_line}")
                
                # Navigate to the location for preview
                try:
                    # Check if file is already open
                    target_view = None
                    for view in self.window.views():
                        if view.file_name() == result['file']:
                            target_view = view
                            break
                    
                    if target_view:
                        # File is already open, just navigate within it
                        log.debug(f"Previewing in already open file: {result['relative_path']}:{result['line_num']}")
                        
                        # Calculate the point for the line
                        point = target_view.text_point(result['line_num'] - 1, 0)
                        
                        # Clear selection and move to the line
                        target_view.sel().clear()
                        target_view.sel().add(point)
                        
                        # Show the location with some context
                        target_view.show_at_center(point)
                        
                        # Make sure this view is visible (but don't focus it)
                        self.window.focus_view(target_view)
                        
                    else:
                        # File is not open, open it as transient for preview
                        log.debug(f"Opening transient preview: {result['relative_path']}:{result['line_num']}")
                        preview_view = self.window.open_file(
                            f"{result['file']}:{result['line_num']}",
                            sublime.ENCODED_POSITION | sublime.TRANSIENT
                        )
                        
                        # Wait a moment for the file to load, then center the view
                        def center_preview():
                            if not preview_view.is_loading():
                                point = preview_view.text_point(result['line_num'] - 1, 0)
                                preview_view.show_at_center(point)
                            else:
                                sublime.set_timeout(center_preview, 10)
                        
                        sublime.set_timeout(center_preview, 10)
                        
                except Exception as e:
                    log.debug(f"Error in preview navigation: {e}")
            else:
                # Clear status when no item is highlighted
                sublime.status_message("")

        # Show quick panel with header and live preview
        self.window.show_quick_panel(
            panel_items, 
            on_done, 
            flags=sublime.MONOSPACE_FONT,
            on_highlight=on_highlight,
            placeholder=header_text
        )

    def input(self, args):
        """Provide input handler for tag filter."""
        if "tag_filter" not in args:
            return TagFilterInputHandler()
        return None

    def input_description(self):
        """Description for the input handler."""
        return "Tag Filter (optional)"


class TagFilterInputHandler(sublime_plugin.ListInputHandler):
    """Input handler for tag filter selection."""

    def name(self):
        return "tag_filter"

    def placeholder(self):
        return "Select tag type to filter (or leave blank for all)"

    def list_items(self):
        """Return list of available tag types."""
        items = [
            sublime.ListInputItem("All Tags", None, "Show all comment tags")
        ]

        # Add each available tag type
        for tag_name in settings.tag_regex.keys():
            # Get the tag definition for more info
            tag_def = settings.tags.get(tag_name, {})
            identifier = tag_def.get('identifier', tag_name)

            items.append(
                sublime.ListInputItem(
                    f"{tag_name} Tags",
                    tag_name,
                    f"Show only {tag_name} tags (identifier: {identifier})"
                )
            )

        return items


class ColoredCommentsListCurrentFileTagsCommand(sublime_aio.WindowCommand):
    """Quick command to list tags in current file only."""

    async def run(self, tag_filter=None):
        """Run tag listing for current file only."""
        # Delegate to main command with current_file_only=True
        await ColoredCommentsListTagsCommand(self.window).run(
            tag_filter=tag_filter,
            current_file_only=True
        )

    def input(self, args):
        """Provide input handler for tag filter."""
        if "tag_filter" not in args:
            return TagFilterInputHandler()
        return None


class ColoredCommentsToggleDebugCommand(sublime_plugin.WindowCommand):
    """Command to toggle debug logging."""

    def run(self):
        log.debug("ColoredCommentsToggleDebugCommand.run() called")
        current_debug = settings.debug
        new_debug = not current_debug

        # Update the setting
        settings_obj = sublime.load_settings("colored_comments.sublime-settings")
        settings_obj.set("debug", new_debug)
        sublime.save_settings("colored_comments.sublime-settings")

        # Update logger
        log.set_debug_logging(new_debug)

        status = "enabled" if new_debug else "disabled"
        message = f"Debug logging {status}"
        sublime.status_message(f"Colored Comments: {message}")
        log.debug(message)


class ColoredCommentsShowLogsCommand(sublime_plugin.WindowCommand):
    """Command to show debug logs in an output panel."""

    def run(self):
        log.debug("ColoredCommentsShowLogsCommand.run() called")
        if not settings.debug:
            sublime.message_dialog(
                "Debug logging is currently disabled.\n\n"
                "Enable debug logging first using:\n"
                "Command Palette → 'Colored Comments: Toggle Debug Logging'"
            )
            return
        log.dump_logs_to_panel(self.window)

    def is_enabled(self):
        """Only enable this command when debug mode is active."""
        return settings.debug


def plugin_loaded() -> None:
    """Handle plugin loading."""
    log.debug("plugin_loaded() called")
    load_settings()
    log.set_debug_logging(settings.debug)
    log.debug(f"Colored Comments v{VERSION} loaded with sublime_aio support")
    log.debug(f"Settings loaded: debug={settings.debug}, debounce_delay={settings.debounce_delay}")
    log.debug(f"Disabled syntax: {settings.disabled_syntax}")
    log.debug(f"Tag regex patterns: {list(settings.tag_regex.keys())}")
    sublime.status_message("Colored Comments: Async support enabled")


def plugin_unloaded() -> None:
    """Handle plugin unloading."""
    log.debug("plugin_unloaded() called")
    unload_settings()
    log.debug("Colored Comments unloaded")
