import sublime
import sublime_plugin
import asyncio
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

import sublime_aio

from .plugin import logger as log
from sublime_lib import ResourcePath
from .plugin.settings import load_settings, settings, unload_settings
from .templates import SCHEME_TEMPLATE

NAME = "Colored Comments"
VERSION = "4.0.1"

comment_selector = "comment - punctuation.definition.comment"
KIND_SCHEME = (sublime.KIND_ID_VARIABLE, "s", "Scheme")
DEFAULT_CS = 'Packages/Color Scheme - Default/Mariana.sublime-color-scheme'


@dataclass
class TagResult:
    """Data class for tag scan results."""
    tag: str
    line: str
    line_num: int
    file: str
    relative_path: str = field(init=False)

    def __post_init__(self):
        try:
            # Try to get relative path from first project folder
            folders = sublime.active_window().folders() if sublime.active_window() else []
            if folders:
                self.relative_path = str(Path(self.file).relative_to(Path(folders[0])))
            else:
                self.relative_path = Path(self.file).name
        except (ValueError, AttributeError):
            self.relative_path = Path(self.file).name


class BaseCommentProcessor:
    """Base class for comment processing functionality."""

    def __init__(self, view: sublime.View):
        self.view = view

    def should_process_view(self) -> bool:
        """Check if view should be processed based on syntax settings."""
        syntax = self.view.settings().get("syntax")
        should_process = syntax not in settings.disabled_syntax
        log.debug(f"View {self.view.id()} syntax check: {syntax}, should_process: {should_process}")
        return should_process

    def find_comment_regions(self) -> List[sublime.Region]:
        """Find all comment regions in the view."""
        regions = self.view.find_by_selector(comment_selector)
        log.debug(f"View {self.view.id()} found {len(regions)} comment regions")
        return regions


class CommentDecorationManager(BaseCommentProcessor):
    """Manages comment decorations with optimized processing."""

    def __init__(self, view: sublime.View):
        super().__init__(view)
        self._last_change_count = 0
        self._last_region_row = -1
        self._processing = False
        log.debug(f"CommentDecorationManager created for view {view.id()}")

    def needs_update(self) -> bool:
        """Check if view needs update and update change count."""
        current_change = self.view.change_count()
        needs_update = current_change != self._last_change_count
        self._last_change_count = current_change
        log.debug(f"View {self.view.id()} needs update: {needs_update}")
        return needs_update

    async def process_comment_line(self, line: str, reg: sublime.Region, line_num: int,
                                 to_decorate: Dict[str, List[sublime.Region]],
                                 prev_match: str = "") -> Optional[str]:
        """Process a single comment line for decoration."""
        if not (stripped_line := line.strip()):
            return None

        if not settings.get_matching_pattern().startswith(" "):
            line = stripped_line

        # Check adjacency for continuation
        current_row = line_num - 1
        is_adjacent = (self._last_region_row != -1 and
                      current_row == self._last_region_row + 1)

        # Try tag patterns first
        for identifier, regex in settings.tag_regex.items():
            if regex.search(line.strip()):
                to_decorate.setdefault(identifier, []).append(reg)
                self._last_region_row = current_row
                log.debug(f"Matched tag '{identifier}' at line: {stripped_line[:50]}...")
                return identifier

        # Check for continuation
        if (prev_match and is_adjacent and
            ((settings.continued_matching and line.startswith(settings.get_matching_pattern())) or
             settings.auto_continue_highlight)):
            to_decorate.setdefault(prev_match, []).append(reg)
            self._last_region_row = current_row
            log.debug(f"Continued tag '{prev_match}' at line: {stripped_line[:50]}...")
            return prev_match

        return None

    def apply_region_styles(self, to_decorate: Dict[str, List[sublime.Region]]):
        """Apply visual styles to decorated regions."""
        total_regions = sum(len(regions) for regions in to_decorate.values())
        log.debug(f"Applying styles to {total_regions} regions across {len(to_decorate)} tag types")

        for identifier, regions in to_decorate.items():
            if tag := settings.tags.get(identifier):
                self.view.add_regions(
                    identifier.lower(),
                    regions,
                    settings.get_scope_for_region(identifier, tag),
                    icon=settings.get_icon(),
                    flags=settings.get_flags(tag)
                )

    def clear_decorations(self):
        """Clear all existing decorations."""
        log.debug(f"Clearing decorations for view {self.view.id()}")
        for key in settings.region_keys:
            self.view.erase_regions(key)

    async def apply_decorations(self):
        """Apply decorations asynchronously with batching."""
        if self._processing or not self.should_process_view():
            return

        self._processing = True
        try:
            # Check if update is needed
            needs_update = self.needs_update()
            has_existing = any(len(self.view.get_regions(key)) > 0 for key in settings.region_keys)

            if not needs_update and has_existing:
                return

            self.clear_decorations()
            to_decorate: Dict[str, List[sublime.Region]] = {}
            prev_match = ""
            self._last_region_row = -1

            # Process comment regions in batches
            for region in self.find_comment_regions():
                for reg in self.view.split_by_newlines(region):
                    line = self.view.substr(reg)
                    line_num = self.view.rowcol(reg.begin())[0] + 1

                    if result := await self.process_comment_line(line, reg, line_num, to_decorate, prev_match):
                        prev_match = result

            self.apply_region_styles(to_decorate)
            log.debug(f"Decoration process complete for view {self.view.id()}")

        except Exception as e:
            log.debug(f"Error in apply_decorations: {e}")
        finally:
            self._processing = False


class FileScanner:
    """Handles file scanning operations with optimized filtering."""

    @classmethod
    def should_skip_file(cls, file_path: Path) -> bool:
        """Check if file should be skipped."""
        return (file_path.suffix.lower() in settings.skip_extensions or
                any(part in settings.skip_dirs for part in file_path.parts))

    @classmethod
    async def get_project_files(cls, folders: List[str]) -> List[Path]:
        """Get all valid text files from project folders."""
        files = []
        for folder in folders:
            folder_path = Path(folder)
            try:
                all_files = list(folder_path.rglob('*'))
                valid_files = [
                    f for f in all_files
                    if f.is_file() and not cls.should_skip_file(f)
                ]
                files.extend(valid_files)

                # Yield control periodically for large directories
                if len(all_files) > 1000:
                    await asyncio.sleep(0.01)

            except (OSError, PermissionError) as e:
                log.debug(f"Error scanning folder {folder_path}: {e}")

        return files


class AsyncTagScanner(BaseCommentProcessor):
    """Async tag scanner with optimized file processing."""

    def __init__(self, window: sublime.Window):
        self.window = window
        log.debug(f"AsyncTagScanner created for window {window.id()}")

    async def scan_for_tags(self, *, tag_filter: Optional[str] = None,
                          current_file_only: bool = False) -> List[TagResult]:
        """Scan for tags with optimized batch processing."""
        files = await self._get_files_to_scan(current_file_only)
        if not files:
            return []

        results = []
        batch_size = 10

        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            batch_tasks = [self._scan_file(file_path, tag_filter) for file_path in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, list):
                    results.extend(result)

            # Update progress
            progress = min(100, int(((i + batch_size) / len(files)) * 100))
            sublime.status_message(f"Scanning tags... {progress}% ({len(results)} found)")
            await asyncio.sleep(0.01)

        return results

    async def _get_files_to_scan(self, current_file_only: bool) -> List[Path]:
        """Get files to scan based on scope."""
        if current_file_only:
            if (view := self.window.active_view()) and (file_name := view.file_name()):
                return [Path(file_name)]
            return []

        folders = self.window.folders()
        return await FileScanner.get_project_files(folders) if folders else []

    @asynccontextmanager
    async def _get_view_for_file(self, file_path: Path):
        """Context manager for getting a view for a file."""
        # Check if already open
        for view in self.window.views():
            if view.file_name() == str(file_path):
                yield view
                return

        # Create temporary panel
        temp_panel = None
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            temp_panel = self.window.create_output_panel('_colored_comments_temp_view')
            temp_panel.run_command('append', {'characters': content})

            if syntax := sublime.find_syntax_for_file(str(file_path)):
                temp_panel.assign_syntax(syntax)

            yield temp_panel
        finally:
            if temp_panel:
                self.window.destroy_output_panel('_colored_comments_temp_view')

    async def _scan_file(self, file_path: Path, tag_filter: Optional[str]) -> List[TagResult]:
        """Scan a single file for tags."""
        results = []
        try:
            async with self._get_view_for_file(file_path) as view:
                if not view:
                    return results

                # Use base class functionality
                super().__init__(view)
                if not self.should_process_view():
                    return results

                for region in self.find_comment_regions():
                    for reg in view.split_by_newlines(region):
                        line = view.substr(reg)
                        line_num = view.rowcol(reg.begin())[0] + 1

                        if tag_results := await self._process_comment_line(line, line_num, file_path, tag_filter):
                            results.extend(tag_results)

        except Exception as e:
            log.debug(f"Error scanning file {file_path}: {e}")

        return results

    async def _process_comment_line(self, line: str, line_num: int, file_path: Path,
                                  tag_filter: Optional[str]) -> List[TagResult]:
        """Process a comment line for tags."""
        if not (stripped_line := line.strip()):
            return []

        if not settings.get_matching_pattern().startswith(" "):
            line = stripped_line

        results = []
        for tag_name, regex in settings.tag_regex.items():
            if tag_filter and tag_name.lower() != tag_filter.lower():
                continue

            if regex.search(line.strip()):
                results.append(TagResult(
                    tag=tag_name,
                    line=stripped_line,
                    line_num=line_num,
                    file=str(file_path)
                ))

        return results


class QuickPanelBuilder:
    """Builder for creating enhanced quick panel items."""

    TAG_KINDS = {
        'TODO': (sublime.KIND_ID_FUNCTION, "T", "Todo"),
        'FIXME': (sublime.KIND_ID_VARIABLE, "F", "Fix Me"),
        'Important': (sublime.KIND_ID_MARKUP, "!", "Important"),
        'Question': (sublime.KIND_ID_NAMESPACE, "?", "Question"),
        'Deprecated': (sublime.KIND_ID_TYPE, "D", "Deprecated"),
        'UNDEFINED': (sublime.KIND_ID_SNIPPET, "U", "Undefined"),
    }

    @classmethod
    def create_tag_panel_items(cls, results: List[TagResult]) -> List[sublime.QuickPanelItem]:
        """Create quick panel items for tag results."""
        return [cls._create_tag_item(result) for result in results]

    @classmethod
    def _create_tag_item(cls, result: TagResult) -> sublime.QuickPanelItem:
        """Create a single quick panel item for a tag result."""
        kind = cls.TAG_KINDS.get(result.tag, (sublime.KIND_ID_MARKUP, "C", "Comment"))
        comment_text = result.line.strip()

        if len(comment_text) > 120:
            comment_text = comment_text[:117] + "..."

        trigger = f"[{result.tag}] {comment_text}"
        annotation = f"{result.relative_path}:{result.line_num}"

        tag_emoji = settings.get_icon_emoji(result.tag)
        file_icon = "📄" if result.file.endswith('.py') else "📝"

        details = [
            f"<div style='padding: 2px 0;'>"
            f"<span style='color: var(--accent);'>{tag_emoji} {result.tag}</span> "
            f"<span style='color: var(--foreground);'>in</span> "
            f"<span style='color: var(--bluish);'>{file_icon} {result.relative_path}</span>"
            f"</div>",

            f"<div style='padding: 2px 0; font-size: 0.9em; color: var(--foreground);'>"
            f"<span style='color: var(--accent);'>Line {result.line_num}:</span> "
            f"<code style='background: var(--background); padding: 1px 3px; border-radius: 2px;'>"
            f"{sublime.html.escape(comment_text)}"
            f"</code>"
            f"</div>"
        ]

        return sublime.QuickPanelItem(
            trigger=trigger,
            details=details,
            annotation=annotation,
            kind=kind
        )


class ViewportManager:
    """Manages viewport positions for preview functionality."""

    def __init__(self, window: sublime.Window):
        self.window = window
        self.original_positions = {}
        self._store_original_positions()

    def _store_original_positions(self):
        """Store original viewport positions for all open views."""
        for view in self.window.views():
            if view.file_name():
                self.original_positions[view.file_name()] = {
                    'viewport_position': view.viewport_position(),
                    'selection': [r for r in view.sel()],
                    'view_id': view.id()
                }

    def restore_original_positions(self):
        """Restore all views to their original positions."""
        for file_path, pos_data in self.original_positions.items():
            for view in self.window.views():
                if (view.file_name() == file_path and
                    view.id() == pos_data['view_id']):
                    view.set_viewport_position(pos_data['viewport_position'], False)
                    view.sel().clear()
                    for region in pos_data['selection']:
                        view.sel().add(region)
                    break

    def preview_location(self, result: TagResult):
        """Preview a location with enhanced status display."""
        tag_emoji = settings.get_icon_emoji(result.tag)
        preview_line = result.line.strip()[:100]
        sublime.status_message(f"{tag_emoji} [{result.tag}] {preview_line}")

        # Navigate to location
        target_view = self._find_view_for_file(result.file)
        if target_view:
            self._navigate_existing_view(target_view, result.line_num)
        else:
            self._open_transient_preview(result)

    def _find_view_for_file(self, file_path: str) -> Optional[sublime.View]:
        """Find existing view for a file."""
        return next((v for v in self.window.views() if v.file_name() == file_path), None)

    def _navigate_existing_view(self, view: sublime.View, line_num: int):
        """Navigate within an existing view."""
        point = view.text_point(line_num - 1, 0)
        view.sel().clear()
        view.sel().add(point)
        view.show_at_center(point)
        self.window.focus_view(view)

    def _open_transient_preview(self, result: TagResult):
        """Open file as transient preview."""
        preview_view = self.window.open_file(
            f"{result.file}:{result.line_num}",
            sublime.ENCODED_POSITION | sublime.TRANSIENT
        )

        def center_preview():
            if not preview_view.is_loading():
                point = preview_view.text_point(result.line_num - 1, 0)
                preview_view.show_at_center(point)
            else:
                sublime.set_timeout(center_preview, 10)

        sublime.set_timeout(center_preview, 10)


# Simplified Command Classes using the new structure

class ColoredCommentsEditSchemeCommand(sublime_plugin.WindowCommand):
    """Command to edit color scheme with enhanced scheme selection."""

    def run(self):
        current_scheme = self._get_current_scheme()
        schemes = self._get_available_schemes(current_scheme)

        def on_done(i):
            if i >= 0:
                self._open_scheme(schemes[i][2])

        self.window.show_quick_panel(schemes, on_done)

    def _get_current_scheme(self) -> str:
        """Get current color scheme path."""
        view = self.window.active_view()
        scheme = (view.settings().get("color_scheme") if view else None) or \
                sublime.load_settings("Preferences.sublime-settings").get("color_scheme")

        if scheme and not scheme.startswith('Packages/'):
            scheme = '/'.join(['Packages'] + scheme.split('/')[1:]) if '/' in scheme else scheme

        return scheme or DEFAULT_CS

    def _get_available_schemes(self, current_scheme: str) -> List[List[str]]:
        """Get list of available color schemes."""
        schemes = [['Edit Current: ' + current_scheme.split('/')[-1], current_scheme, current_scheme]]

        resources = sublime.find_resources("*.sublime-color-scheme") + sublime.find_resources("*.tmTheme")
        schemes.extend([[r.split('/')[-1], r, r] for r in resources])

        return schemes

    def _open_scheme(self, scheme_path: str):
        """Open and potentially inject template into scheme."""
        try:
            resource = ResourcePath.from_file_path(scheme_path)
            new_view = self.window.open_file(str(resource))

            def check_loaded_and_inject():
                if new_view.is_loading():
                    sublime.set_timeout(check_loaded_and_inject, 50)
                else:
                    self._inject_scheme_template(new_view)

            check_loaded_and_inject()
        except Exception as e:
            log.debug(f"Error opening scheme: {e}")

    def _inject_scheme_template(self, view: sublime.View):
        """Inject scheme template if needed."""
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
    """Optimized event listener using new structure."""

    def __init__(self, view):
        super().__init__(view)
        self.manager = CommentDecorationManager(view)

    @sublime_aio.debounced(settings.debounce_delay)
    async def on_modified(self):
        """Handle view modifications."""
        if self.view.settings().get("syntax") not in settings.disabled_syntax:
            await self.manager.apply_decorations()

    async def on_load(self):
        """Handle view loading."""
        if self.view.settings().get("syntax") not in settings.disabled_syntax:
            await self.manager.apply_decorations()

    async def on_activated(self):
        """Handle view activation."""
        if self.view.settings().get("syntax") not in settings.disabled_syntax:
            await self.manager.apply_decorations()

    def on_close(self):
        """Handle view closing."""
        self.manager.clear_decorations()


class ColoredCommentsCommand(sublime_aio.ViewCommand):
    """Manual decoration command."""

    async def run(self):
        manager = CommentDecorationManager(self.view)
        if not manager.should_process_view():
            sublime.status_message("View type not supported for colored comments")
            return

        manager._last_change_count = 0  # Force update
        await manager.apply_decorations()
        sublime.status_message("Comment decorations applied")


class ColoredCommentsClearCommand(sublime_plugin.TextCommand):
    """Clear decorations command."""

    def run(self, edit):
        CommentDecorationManager(self.view).clear_decorations()
        sublime.status_message("Comment decorations cleared")


class ColoredCommentsListTagsCommand(sublime_aio.WindowCommand):
    """Enhanced tag listing command with optimized processing."""

    async def run(self, tag_filter=None, current_file_only=False):
        if tag_filter and tag_filter not in settings.tag_regex:
            available_tags = ", ".join(settings.tag_regex.keys())
            sublime.error_message(f"Unknown tag filter: '{tag_filter}'\nAvailable tags: {available_tags}")
            return

        scanner = AsyncTagScanner(self.window)

        try:
            sublime.status_message("Scanning for comment tags...")
            results = await scanner.scan_for_tags(tag_filter=tag_filter, current_file_only=current_file_only)

            if results:
                self._show_results(results, tag_filter, current_file_only)
                scope_text = "current file" if current_file_only else "project"
                filter_text = f" (filtered by '{tag_filter}')" if tag_filter else ""
                sublime.status_message(f"Found {len(results)} comment tags in {scope_text}{filter_text}")
            else:
                scope_text = "current file" if current_file_only else "project"
                filter_text = f" matching '{tag_filter}'" if tag_filter else ""
                sublime.status_message(f"No comment tags found in {scope_text}{filter_text}")

        except Exception as e:
            log.debug(f"Error in tag scanning: {e}")
            sublime.error_message(f"Error scanning for tags: {str(e)}")

    def _show_results(self, results: List[TagResult], tag_filter=None, current_file_only=False):
        """Show results using optimized components."""
        results.sort(key=lambda x: (x.tag, x.relative_path, x.line_num))

        viewport_manager = ViewportManager(self.window)
        panel_items = QuickPanelBuilder.create_tag_panel_items(results)

        scope_text = "Current File" if current_file_only else "Project"
        filter_text = f" - {tag_filter} Tags" if tag_filter else " - All Tags"
        header_text = f"{scope_text}{filter_text} ({len(results)} found)"

        def on_done(index):
            if index >= 0:
                result = results[index]
                self.window.open_file(f"{result.file}:{result.line_num}", sublime.ENCODED_POSITION)
            else:
                viewport_manager.restore_original_positions()

        def on_highlight(index):
            if index >= 0:
                viewport_manager.preview_location(results[index])
            else:
                sublime.status_message("")

        self.window.show_quick_panel(
            panel_items, on_done,
            flags=sublime.MONOSPACE_FONT,
            on_highlight=on_highlight,
            placeholder=header_text
        )

    def input(self, args):
        if "tag_filter" not in args:
            return TagFilterInputHandler()
        return None

    def input_description(self):
        return "Tag Filter (optional)"


class TagFilterInputHandler(sublime_plugin.ListInputHandler):
    """Optimized input handler for tag filters."""

    def name(self):
        return "tag_filter"

    def placeholder(self):
        return "Select tag type to filter (or leave blank for all)"

    def list_items(self):
        items = [sublime.ListInputItem("All Tags", None, "Show all comment tags")]

        for tag_name in settings.tag_regex.keys():
            tag_def = settings.tags.get(tag_name, {})
            identifier = tag_def.get('identifier', tag_name)
            items.append(sublime.ListInputItem(
                f"{tag_name} Tags", tag_name,
                f"Show only {tag_name} tags (identifier: {identifier})"
            ))

        return items


class ColoredCommentsListCurrentFileTagsCommand(sublime_aio.WindowCommand):
    """Quick command for current file tags."""

    async def run(self, tag_filter=None):
        await ColoredCommentsListTagsCommand(self.window).run(
            tag_filter=tag_filter, current_file_only=True
        )

    def input(self, args):
        if "tag_filter" not in args:
            return TagFilterInputHandler()
        return None


class ColoredCommentsToggleDebugCommand(sublime_plugin.WindowCommand):
    """Debug toggle command."""

    def run(self):
        new_debug = not settings.debug
        settings_obj = sublime.load_settings("colored_comments.sublime-settings")
        settings_obj.set("debug", new_debug)
        sublime.save_settings("colored_comments.sublime-settings")

        log.set_debug_logging(new_debug)
        status = "enabled" if new_debug else "disabled"
        sublime.status_message(f"Colored Comments: Debug logging {status}")


class ColoredCommentsShowLogsCommand(sublime_plugin.WindowCommand):
    """Show logs command."""

    def run(self):
        if not settings.debug:
            sublime.message_dialog(
                "Debug logging is currently disabled.\n\n"
                "Enable debug logging first using:\n"
                "Command Palette → 'Colored Comments: Toggle Debug Logging'"
            )
            return
        log.dump_logs_to_panel(self.window)

    def is_enabled(self):
        return settings.debug


def plugin_loaded() -> None:
    """Handle plugin loading."""
    load_settings()
    log.set_debug_logging(settings.debug)
    log.debug(f"Colored Comments v{VERSION} loaded with optimized structure")


def plugin_unloaded() -> None:
    """Handle plugin unloading."""
    unload_settings()
    log.debug("Colored Comments unloaded")
