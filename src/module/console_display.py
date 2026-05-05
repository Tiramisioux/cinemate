import errno
import fcntl
import logging
import os


TTY_PATH = "/dev/tty1"
TTY_CANDIDATES = ("/dev/tty", TTY_PATH, "/dev/console")
KDSETMODE = 0x4B3A
KD_TEXT = 0x00
KD_GRAPHICS = 0x01


def _describe_tty_errors(errors: list[tuple[str, OSError]]) -> str:
    return "; ".join(f"{path}: {exc}" for path, exc in errors)


def get_console_tty_path(*, read_write: bool = False) -> str | None:
    flags = (os.O_RDWR if read_write else os.O_WRONLY) | os.O_CLOEXEC
    for path in TTY_CANDIDATES:
        try:
            fd = os.open(path, flags)
        except OSError:
            continue
        else:
            os.close(fd)
            return path
    return None


def _write_tty(text: str):
    tty_path = get_console_tty_path()
    if tty_path is None:
        raise OSError("No writable console TTY available")

    with open(tty_path, "w") as tty:
        tty.write(text)
        tty.flush()


def _set_console_mode(mode: int, label: str) -> bool:
    open_errors: list[tuple[str, OSError]] = []
    for tty_path in TTY_CANDIDATES:
        try:
            fd = os.open(tty_path, os.O_RDWR | os.O_CLOEXEC)
        except OSError as exc:
            open_errors.append((tty_path, exc))
            continue

        try:
            fcntl.ioctl(fd, KDSETMODE, mode)
            return True
        except OSError as exc:
            if exc.errno == errno.EPERM:
                logging.debug(
                    "Could not set %s to %s mode without elevated privileges: %s",
                    tty_path,
                    label,
                    exc,
                )
            else:
                logging.warning("Could not set %s to %s mode: %s", tty_path, label, exc)
            return False
        finally:
            os.close(fd)

    logging.warning(
        "Could not open a console TTY to set %s mode: %s",
        label,
        _describe_tty_errors(open_errors),
    )
    return False


def hide_cursor():
    try:
        _write_tty("\033[?25l")
    except Exception as exc:
        logging.warning("Could not hide cursor: %s", exc)


def show_cursor():
    try:
        _write_tty("\033[?25h")
    except Exception as exc:
        logging.warning("Could not show cursor: %s", exc)


def clear_screen():
    try:
        _write_tty("\033[2J\033[H")
    except Exception as exc:
        logging.warning("Could not clear screen: %s", exc)


def claim_console_for_framebuffer():
    clear_screen()
    hide_cursor()
    return _set_console_mode(KD_GRAPHICS, "graphics")


def release_console_to_text():
    ok = _set_console_mode(KD_TEXT, "text")
    clear_screen()
    show_cursor()
    return ok
