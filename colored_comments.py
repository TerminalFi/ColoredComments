import sublime
import sublime_plugin
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Set
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import threading
import time

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

            self.clear_decorations()
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

                            # Removed async sleep - was causing delays for large directories
            # if len(all_files) > 1000:
            #     await asyncio.sleep(0.01)

            except (OSError, PermissionError) as e:
                log.debug(f"Error scanning folder {folder_path}: {e}")

        return files


class AsyncTagScanner(BaseCommentProcessor):
    """Async tag scanner with optimized file processing."""

    def __init__(self, window: sublime.Window):
        self.window = window
        self._temp_panel = None
        log.debug(f"AsyncTagScanner created for window {window.id()}")

    async def scan_for_tags(self, *, tag_filter: Optional[str] = None,
                          current_file_only: bool = False) -> List[TagResult]:
        """Scan for tags with optimized batch processing."""
        files = await self._get_files_to_scan(current_file_only)
        if not files:
            return []

        results = []
        batch_size = 12  # Larger batch size since async sleeps were removed

        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            
            # Create parallel tasks with unique panel names
            batch_tasks = []
            for j, file_path in enumerate(batch):
                panel_name = f'_colored_comments_temp_view_{i}_{j}'
                batch_tasks.append(self._scan_file_with_unique_panel(file_path, panel_name, tag_filter))
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, list):
                    results.extend(result)

            # Update progress (removed async sleep - was causing delays)
            progress = min(100, int(((i + batch_size) / len(files)) * 100))
            sublime.status_message(f"Scanning tags... {progress}% ({len(results)} found)")
            # await asyncio.sleep(0.01)  # Removed - was causing major delays

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
    async def _get_view_for_file(self, file_path: Path, panel_name: str = '_colored_comments_temp_view'):
        """Context manager for getting a view for a file with unique panel name."""
        # Check if already open
        for view in self.window.views():
            if view.file_name() == str(file_path):
                yield view
                return

        # Create a fresh temp panel for this file
        temp_panel = None
        try:
            # Read file asynchronously to avoid blocking UI
            content = await self._read_file_async(file_path)
            if content is None:
                yield None
                return

            # Create fresh panel for this file with unique name
            temp_panel = self.window.create_output_panel(panel_name)
            temp_panel.run_command('append', {'characters': content})

            if syntax := sublime.find_syntax_for_file(str(file_path)):
                temp_panel.assign_syntax(syntax)

            yield temp_panel
        finally:
            # Immediately destroy the panel after use
            if temp_panel:
                self.window.destroy_output_panel(panel_name)

    async def _read_file_async(self, file_path: Path) -> Optional[str]:
        """Read file content asynchronously to avoid blocking UI."""
        try:
            # Direct file I/O without async sleeps (they were causing 3+ second delays)
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            return content
        except Exception as e:
            log.debug(f"Error reading file {file_path}: {e}")
            return None



    async def _scan_file(self, file_path: Path, tag_filter: Optional[str]) -> List[TagResult]:
        """Scan a single file for tags."""
        return await self._scan_file_with_unique_panel(file_path, '_colored_comments_temp_view', tag_filter)

    async def _scan_file_with_unique_panel(self, file_path: Path, panel_name: str, tag_filter: Optional[str]) -> List[TagResult]:
        """Scan a single file for tags using a unique panel name."""
        results = []
        try:
            async with self._get_view_for_file(file_path, panel_name) as view:
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


class TagIndex:
    """Real-time index of comment tags across the project."""
    
    def __init__(self):
        self._index: Dict[str, List[TagResult]] = {}  # file_path -> [TagResult]
        self._tag_index: Dict[str, List[TagResult]] = {}  # tag_name -> [TagResult]
        self._file_timestamps: Dict[str, float] = {}  # file_path -> last_modified
        self._lock = threading.RLock()
        self._indexed_folders: Set[str] = set()
        self._is_indexing = False
        log.debug("TagIndex initialized")

    def is_indexed(self, folders: List[str]) -> bool:
        """Check if the current project folders are already indexed."""
        with self._lock:
            return set(folders).issubset(self._indexed_folders)

    def is_indexing(self) -> bool:
        """Check if indexing is currently in progress."""
        return self._is_indexing

    async def build_initial_index(self, window: sublime.Window) -> None:
        """Build initial index for all project files."""
        if self._is_indexing:
            sublime.status_message("Tag index already building...")
            return
            
        folders = window.folders()
        if not folders:
            sublime.status_message("No project folders to index")
            return
            
        if self.is_indexed(folders):
            sublime.status_message("Tag index already up to date")
            return

        self._is_indexing = True
        start_time = time.time()
        
        try:
            log.debug(f"Building initial tag index for {len(folders)} folders")
            sublime.status_message("🔍 Initializing tag index...")
            
            scanner = AsyncTagScanner(window)
            
            # Get all files to index
            sublime.status_message("🔍 Scanning project files...")
            files = await FileScanner.get_project_files(folders)
            log.debug(f"Found {len(files)} files to index")
            
            if not files:
                sublime.status_message("No files found to index")
                return
            
            sublime.status_message(f"🔍 Indexing {len(files)} files...")
            
            # Index files in batches - each file gets its own temp panel
            batch_size = 8  # Larger batches since async sleeps were removed
            for i in range(0, len(files), batch_size):
                batch = files[i:i + batch_size]
                
                for file_path in batch:
                    await self._index_file(file_path, scanner)
                    
                # Update progress with more detailed info
                progress = min(100, int(((i + batch_size) / len(files)) * 100))
                current_tags = self.get_total_tag_count()
                files_processed = min(i + batch_size, len(files))
                
                sublime.status_message(
                    f"🔍 Building tag index... {progress}% "
                    f"({files_processed}/{len(files)} files, {current_tags} tags found)"
                )
                # await asyncio.sleep(0.02)  # Removed - was causing major delays
            
            # Mark folders as indexed
            with self._lock:
                self._indexed_folders.update(folders)
                
            # Final status with timing info
            total_tags = self.get_total_tag_count()
            elapsed = time.time() - start_time
            
            if total_tags > 0:
                sublime.status_message(
                    f"✅ Tag index built: {total_tags} tags from {len(files)} files "
                    f"({elapsed:.1f}s)"
                )
            else:
                sublime.status_message("✅ Tag index built: No comment tags found")
                
            log.debug(f"Initial tag index complete: {total_tags} tags across {len(files)} files in {elapsed:.1f}s")
            
            # Clear status after a few seconds
            sublime.set_timeout(lambda: sublime.status_message(""), 5000)
            
        except Exception as e:
            log.debug(f"Error building initial index: {e}")
            sublime.status_message(f"❌ Error building tag index: {str(e)}")
            sublime.set_timeout(lambda: sublime.status_message(""), 5000)
        finally:
            self._is_indexing = False

    async def _index_file(self, file_path: Path, scanner: AsyncTagScanner, force_update: bool = False) -> None:
        """Index a single file and update the index."""
        try:
            file_str = str(file_path)
            
            # Check if file needs indexing (new or modified)
            if not force_update:
                try:
                    current_mtime = file_path.stat().st_mtime
                    with self._lock:
                        if (file_str in self._file_timestamps and 
                            self._file_timestamps[file_str] >= current_mtime):
                            return  # File hasn't changed
                except OSError:
                    # File might not exist anymore
                    self.remove_file_from_index(file_str)
                    return
            
            # Always get fresh timestamp
            try:
                current_mtime = file_path.stat().st_mtime
            except OSError:
                self.remove_file_from_index(file_str)
                return
            
            # Scan file for tags - this will get fresh line numbers
            # Use unique panel name for indexing to avoid conflicts
            panel_name = f'_colored_comments_index_{hash(str(file_path)) % 10000}'
            results = await scanner._scan_file_with_unique_panel(file_path, panel_name, tag_filter=None)
            
            # Update index atomically
            with self._lock:
                # Always remove old entries for this file to ensure fresh line numbers
                self._remove_file_from_internal_index(file_str)
                
                # Add new entries with current line numbers
                if results:
                    self._index[file_str] = results
                    
                    # Update tag index
                    for result in results:
                        if result.tag not in self._tag_index:
                            self._tag_index[result.tag] = []
                        self._tag_index[result.tag].append(result)
                
                # Update timestamp
                self._file_timestamps[file_str] = current_mtime
                
        except Exception as e:
            log.debug(f"Error indexing file {file_path}: {e}")

    def update_file_index(self, file_path: str, window: sublime.Window) -> None:
        """Update index for a specific file (called when file is modified)."""
        if self._is_indexing:
            return
            
        # Run async update in background using sublime_aio
        def on_update_done(future):
            try:
                future.result()
            except Exception as e:
                log.debug(f"Error in file index update callback: {e}")
                
        sublime_aio.run_coroutine(self._update_file_async(file_path, window)).add_done_callback(on_update_done)

    async def _update_file_async(self, file_path: str, window: sublime.Window) -> None:
        """Async helper for updating file index."""
        try:
            path = Path(file_path)
            if not path.exists() or FileScanner.should_skip_file(path):
                with self._lock:
                    if file_path in self._index:
                        self.remove_file_from_index(file_path)
                        sublime.status_message(f"🗑️ Removed {Path(file_path).name} from tag index")
                        sublime.set_timeout(lambda: sublime.status_message(""), 2000)
                return
                
            scanner = AsyncTagScanner(window)
            old_count = len(self._index.get(file_path, []))
            # Force update to ensure fresh line numbers
            await self._index_file(path, scanner, force_update=True)
            new_count = len(self._index.get(file_path, []))
            
            # Show brief status update for significant changes
            if new_count != old_count:
                filename = Path(file_path).name
                if new_count > old_count:
                    sublime.status_message(f"📝 Updated tag index: +{new_count - old_count} tags in {filename}")
                elif old_count > 0:
                    sublime.status_message(f"📝 Updated tag index: -{old_count - new_count} tags in {filename}")
                else:
                    sublime.status_message(f"📝 Updated tag index: {filename}")
                sublime.set_timeout(lambda: sublime.status_message(""), 3000)
            
            log.debug(f"Updated index for file: {file_path} ({old_count} -> {new_count} tags)")
            
        except Exception as e:
            log.debug(f"Error updating file index for {file_path}: {e}")
            sublime.status_message(f"❌ Error updating tag index for {Path(file_path).name}")
            sublime.set_timeout(lambda: sublime.status_message(""), 3000)

    def remove_file_from_index(self, file_path: str) -> None:
        """Remove a file from the index (when deleted)."""
        with self._lock:
            self._remove_file_from_internal_index(file_path)
            self._file_timestamps.pop(file_path, None)

    def _remove_file_from_internal_index(self, file_path: str) -> None:
        """Internal method to remove file from index (assumes lock is held)."""
        # Remove from main index
        old_results = self._index.pop(file_path, [])
        
        # Remove from tag index
        for result in old_results:
            if result.tag in self._tag_index:
                self._tag_index[result.tag] = [
                    r for r in self._tag_index[result.tag] 
                    if r.file != file_path
                ]
                if not self._tag_index[result.tag]:
                    del self._tag_index[result.tag]

    def get_all_tags(self, tag_filter: Optional[str] = None, current_file_only: bool = False, 
                    current_file_path: Optional[str] = None) -> List[TagResult]:
        """Get all tags from the index."""
        with self._lock:
            results = []
            
            if current_file_only and current_file_path:
                # Get tags only from current file
                results = self._index.get(current_file_path, [])
            else:
                # Get all tags
                if tag_filter and tag_filter in self._tag_index:
                    results = self._tag_index[tag_filter][:]
                else:
                    for file_results in self._index.values():
                        results.extend(file_results)
            
            # Apply tag filter if specified and not using tag index
            if tag_filter and not current_file_only:
                results = [r for r in results if r.tag.lower() == tag_filter.lower()]
            
            return results

    def get_total_tag_count(self) -> int:
        """Get total number of tags in the index."""
        with self._lock:
            return sum(len(results) for results in self._index.values())

    def clear_index(self) -> None:
        """Clear the entire index."""
        with self._lock:
            self._index.clear()
            self._tag_index.clear()
            self._file_timestamps.clear()
            self._indexed_folders.clear()
            log.debug("Tag index cleared")


# Global tag index instance
tag_index = TagIndex()


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
            
            # Update tag index for this file if it has a file path
            if self.view.file_name():
                tag_index.update_file_index(self.view.file_name(), self.view.window())

    async def on_load(self):
        """Handle view loading."""
        if self.view.settings().get("syntax") not in settings.disabled_syntax:
            await self.manager.apply_decorations()
            
            # Check if we need to build index when loading files in a project
            if self.view.file_name() and self.view.window() and self.view.window().folders():
                if not tag_index.is_indexed(self.view.window().folders()):
                    def on_index_done(future):
                        try:
                            future.result()
                        except Exception as e:
                            log.debug(f"Error building index on file load: {e}")
                    
                    sublime_aio.run_coroutine(
                        tag_index.build_initial_index(self.view.window())
                    ).add_done_callback(on_index_done)

    async def on_activated(self):
        """Handle view activation."""
        if self.view.settings().get("syntax") not in settings.disabled_syntax:
            await self.manager.apply_decorations()

    def on_close(self):
        """Handle view closing."""
        self.manager.clear_decorations()


class ColoredCommentsWindowEventListener(sublime_plugin.EventListener):
    """Window-level event listener for tag index management."""

    def on_window_command(self, window, command_name, args):
        """Handle window commands that might affect project structure."""
        if command_name in ['new_window', 'close_window', 'open_project', 'close_project']:
            # Delay to let the window/project state settle
            sublime.set_timeout(lambda: self._check_index_for_window(window), 200)

    def on_load_project(self, window):
        """Handle project loading."""
        sublime.set_timeout(lambda: self._check_index_for_window(window), 300)

    def on_activated(self, view):
        """Handle view activation - check if we need to build index."""
        if view and view.window() and view.window().folders():
            window = view.window()
            if not tag_index.is_indexed(window.folders()) and not tag_index.is_indexing():
                def on_index_done(future):
                    try:
                        future.result()
                    except Exception as e:
                        log.debug(f"Error building index on view activation: {e}")
                
                sublime_aio.run_coroutine(
                    tag_index.build_initial_index(window)
                ).add_done_callback(on_index_done)

    def _check_index_for_window(self, window):
        """Check if window needs index building."""
        if window and window.folders():
            if not tag_index.is_indexed(window.folders()) and not tag_index.is_indexing():
                def on_index_done(future):
                    try:
                        future.result()
                    except Exception as e:
                        log.debug(f"Error building index for window: {e}")
                
                sublime_aio.run_coroutine(
                    tag_index.build_initial_index(window)
                ).add_done_callback(on_index_done)


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


class ColoredCommentsListTagsCommand(sublime_aio.WindowCommand):
    """Enhanced tag listing command with optimized processing."""

    async def run(self, tag_filter=None, current_file_only=False):
        if tag_filter and tag_filter not in settings.tag_regex:
            available_tags = ", ".join(settings.tag_regex.keys())
            sublime.error_message(f"Unknown tag filter: '{tag_filter}'\nAvailable tags: {available_tags}")
            return

        try:
            # Check if we need to build initial index
            if not tag_index.is_indexed(self.window.folders()) and not tag_index.is_indexing():
                sublime.status_message("🔍 Tag index not found, building now...")
                await tag_index.build_initial_index(self.window)
            elif tag_index.is_indexing():
                sublime.status_message("⏳ Waiting for tag index to complete...")
                # Wait for indexing to complete
                while tag_index.is_indexing():
                    await asyncio.sleep(0.1)

            # Get current file path for current_file_only mode
            current_file_path = None
            if current_file_only:
                active_view = self.window.active_view()
                if active_view and active_view.file_name():
                    current_file_path = active_view.file_name()

            # Get results from index (very fast!)
            scope_text = "current file" if current_file_only else "project"
            filter_text = f" ({tag_filter} tags)" if tag_filter else ""
            sublime.status_message(f"📋 Loading {scope_text} tags{filter_text}...")
            
            results = tag_index.get_all_tags(
                tag_filter=tag_filter, 
                current_file_only=current_file_only,
                current_file_path=current_file_path
            )

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
            log.debug(f"Error in tag listing: {e}")
            sublime.error_message(f"Error listing tags: {str(e)}")

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
    
    # Initialize tag index for open windows using sublime_aio
    async def initialize_index_with_delay(delay_ms: int):
        """Initialize index after a delay to let Sublime settle."""
        await asyncio.sleep(delay_ms / 1000.0)  # Convert ms to seconds
        
        windows_with_folders = [w for w in sublime.windows() if w.folders()]
        if windows_with_folders:
            log.debug(f"Initializing tag index for {len(windows_with_folders)} windows with projects (attempt after {delay_ms}ms)")
            
            # Process windows concurrently
            tasks = []
            for window in windows_with_folders:
                if not tag_index.is_indexed(window.folders()):
                    tasks.append(asyncio.create_task(tag_index.build_initial_index(window)))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                log.debug(f"Completed initialization for {len(tasks)} windows")
            else:
                log.debug("All windows already indexed")
        else:
            log.debug(f"No windows with project folders found after {delay_ms}ms delay")

    async def initialize_plugin():
        """Initialize plugin with multiple attempts."""
        log.debug("Starting tag index initialization...")
        
        # Try initialization at different delays to catch windows that load slowly
        init_tasks = [
            asyncio.create_task(initialize_index_with_delay(500)),   # Quick attempt
            asyncio.create_task(initialize_index_with_delay(1500))   # Delayed attempt
        ]
        
        await asyncio.gather(*init_tasks, return_exceptions=True)
        log.debug("Plugin initialization tasks completed")

    def on_initialization_done(future):
        """Callback when initialization completes."""
        try:
            future.result()  # This will raise any exceptions that occurred
            log.debug("Tag index initialization completed successfully")
        except Exception as e:
            log.debug(f"Tag index initialization failed: {e}")

    # Initialize plugin on asyncio event loop
    sublime_aio.run_coroutine(initialize_plugin()).add_done_callback(on_initialization_done)


def plugin_unloaded() -> None:
    """Handle plugin unloading."""
    unload_settings()
    tag_index.clear_index()
    log.debug("Colored Comments unloaded")
