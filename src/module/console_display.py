import fcntl
import logging
import os
import errno


TTY_PATH = "/dev/tty1"
KDSETMODE = 0x4B3A
KD_TEXT = 0x00
KD_GRAPHICS = 0x01


def _write_tty(text: str):
    with open(TTY_PATH, "w") as tty:
        tty.write(text)
        tty.flush()


def _set_console_mode(mode: int, label: str) -> bool:
    try:
        fd = os.open(TTY_PATH, os.O_RDWR | os.O_CLOEXEC)
    except OSError as exc:
        logging.warning("Could not open %s to set %s mode: %s", TTY_PATH, label, exc)
        return False

    try:
        fcntl.ioctl(fd, KDSETMODE, mode)
        return True
    except OSError as exc:
        if exc.errno == errno.EPERM:
            logging.debug(
                "Could not set %s to %s mode without elevated privileges: %s",
                TTY_PATH,
                label,
                exc,
            )
        else:
            logging.warning("Could not set %s to %s mode: %s", TTY_PATH, label, exc)
        return False
    finally:
        os.close(fd)


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
