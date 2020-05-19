log_debug = False
log_exceptions = True


def set_debug_logging(logging_enabled: bool) -> None:
    global log_debug
    log_debug = logging_enabled


def debug(msg: str) -> None:
    if log_debug:
        printf(msg)


def printf(msg: str, prefix: str = "Colored Comments") -> None:
    print(f"{prefix}:{msg}")
