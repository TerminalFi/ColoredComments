log_debug = False
log_exceptions = True
_log_buffer = []
_MAX_LOG_BUFFER = 1000  # Maximum number of log entries to keep in memory


def set_debug_logging(logging_enabled: bool) -> None:
    global log_debug
    log_debug = logging_enabled


def debug(msg: str) -> None:
    if log_debug:
        _log_buffer.append(msg)
        if len(_log_buffer) > _MAX_LOG_BUFFER:
            _log_buffer.pop(0)  # Remove oldest entry
        printf(msg)


def printf(msg: str, prefix: str = "Colored Comments") -> None:
    print(f"{prefix}:{msg}")


def dump_logs_to_panel(window) -> None:
    """Dump the log buffer to an output panel.
    
    Args:
        window: The Sublime Text window to create the panel in
    """
    if not window:
        return
        
    panel = window.create_output_panel('colored_comments_logs')
    panel.set_read_only(False)
    panel.run_command('erase_view')
    
    # Add a header
    panel.run_command('append', {'characters': "=== Colored Comments Debug Logs ===\n\n"})
    
    # Add each log entry
    for entry in _log_buffer:
        panel.run_command('append', {'characters': f"{entry}\n"})
    
    panel.set_read_only(True)
    
    # Show the panel
    window.run_command('show_panel', {'panel': 'output.colored_comments_logs'})
