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


class CommentDecorationManager:
    """Manages the decoration of comments in a view with async support."""

    def __init__(self, view):
        self.view = view
        self._last_change_count = 0
        self._last_region_row = -1
        self._processing = False
        log.debug(f"CommentDecorationManager created for view {view.id()}: {view.file_name()}")

    def should_process_view(self):
        """Check if the view needs to be processed based on syntax settings."""
        syntax = self.view.settings().get("syntax")
        should_process = syntax not in settings.disabled_syntax
        log.debug(f"View {self.view.id()} syntax check: {syntax}, should_process: {should_process}")
        return should_process

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
        regions = self.view.find_by_selector(comment_selector)
        log.debug(f"View {self.view.id()} found {len(regions)} comment regions using selector: {comment_selector}")
        return regions

    def process_comment_line(self, line, to_decorate, reg, prev_match):
        """Process a single comment line and identify its tag."""
        stripped_line = line.strip()
        if not stripped_line:
            return ""

        if not settings.get_matching_pattern().startswith(" "):
            line = stripped_line

        # Check adjacency for continuation
        is_adjacent = False
        if self._last_region_row != -1:
            current_row, _ = self.view.rowcol(reg.begin())
            is_adjacent = current_row == self._last_region_row + 1

        # Try to match tag patterns first
        for identifier in settings.tag_regex:
            if settings.get_regex(identifier).search(line.strip()):
                to_decorate.setdefault(identifier, []).append(reg)
                self._last_region_row, _ = self.view.rowcol(reg.end())
                log.debug(f"View {self.view.id()} matched tag '{identifier}' at line: {stripped_line[:50]}...")
                return identifier

        # Check for continuation
        if prev_match and is_adjacent and (
            (settings.continued_matching and line.startswith(settings.get_matching_pattern())) or
            settings.auto_continue_highlight
        ):
            to_decorate.setdefault(prev_match, []).append(reg)
            self._last_region_row, _ = self.view.rowcol(reg.end())
            log.debug(f"View {self.view.id()} continued tag '{prev_match}' at line: {stripped_line[:50]}...")
            return prev_match

        return ""

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

            comment_regions = self.find_comment_regions()

            if not comment_regions:
                log.debug(f"View {self.view.id()} no comment regions found")
                return

            # Process in batches to maintain UI responsiveness
            batch_size = 100
            total_processed = 0

            for i in range(0, len(comment_regions), batch_size):
                batch = comment_regions[i:i + batch_size]
                log.debug(f"View {self.view.id()} processing batch {i//batch_size + 1}, regions {i} to {i + len(batch)}")

                batch_processed = 0
                for region in batch:
                    for reg in self.view.split_by_newlines(region):
                        line = self.view.substr(reg)
                        result = self.process_comment_line(line, to_decorate, reg, prev_match)
                        prev_match = result if result else prev_match
                        batch_processed += 1

                total_processed += batch_processed
                log.debug(f"View {self.view.id()} batch complete, processed {batch_processed} lines, total: {total_processed}")

                # Yield control after each batch to keep UI responsive
                if i + batch_size < len(comment_regions):
                    await asyncio.sleep(0.001)

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
        """Scan a single file for comment tags."""
        results = []

        try:
            # Read file with proper encoding handling
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            log.debug(f"Scanning file {file_path} with {len(lines)} lines")

            # Process lines in batches for large files
            batch_size = 200
            file_tags = 0
            for i in range(0, len(lines), batch_size):
                batch_lines = lines[i:i + batch_size]

                for line_offset, line in enumerate(batch_lines):
                    line_num = i + line_offset + 1
                    found = await self._process_line(line, line_num, file_path, tag_filter, results)
                    if found:
                        file_tags += 1

                # Yield control for large files
                if i + batch_size < len(lines):
                    await asyncio.sleep(0.001)

            if file_tags > 0:
                log.debug(f"File {file_path.name} contains {file_tags} tags")

        except Exception as e:
            log.debug(f"Error scanning file {file_path}: {e}")

        return results

    async def _process_line(self, line, line_num, file_path, tag_filter, results):
        """Process a single line for tag matches."""
        stripped_line = line.strip()
        if not stripped_line:
            return False

        found = False
        for tag_name, regex in settings.tag_regex.items():
            # Apply tag filter if specified
            if tag_filter and tag_name.lower() != tag_filter.lower():
                continue

            if regex.search(stripped_line):
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
                found = True

        return found

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
        scanner = AsyncTagScanner(self.window)

        sublime.status_message("Scanning for comment tags...")
        results = await scanner.scan_for_tags(tag_filter, current_file_only)

        if results:
            log.debug(f"Showing {len(results)} tag results")
            self._show_results(results)
            sublime.status_message(f"Found {len(results)} comment tags")
        else:
            log.debug("No comment tags found")
            sublime.status_message("No comment tags found")
            sublime.message_dialog("No comment tags found in the current scope.")

    def _show_results(self, results):
        """Show results in a quick panel with navigation."""
        panel_items = []
        for result in results:
            # Truncate long lines for better display
            tag_line = result['line'].strip()[:80]
            if len(result['line'].strip()) > 80:
                tag_line += "..."

            panel_items.append([
                f"[{result['tag']}] {tag_line}",
                f"{result['relative_path']}:{result['line_num']}"
            ])

        def on_done(index):
            if index >= 0:
                result = results[index]
                log.debug(f"Opening file at {result['file']}:{result['line_num']}")
                # Open file at specific line
                self.window.open_file(
                    f"{result['file']}:{result['line_num']}",
                    sublime.ENCODED_POSITION
                )

        self.window.show_quick_panel(panel_items, on_done)


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
