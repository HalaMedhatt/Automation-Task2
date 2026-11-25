import ctypes
import logging
import struct
import time

import win32api
import win32con
import win32gui

from pywinauto import Desktop,clipboard, mouse

logger = logging.getLogger(__name__)

ACTION_DELAY = 0.5
MAX_ROWS = 500
CLIPBOARD_TIMEOUT = 3

FIELDS = (
    "customer_id",
    "first_name",
    "last_name",
    "company",
    "zip",
    "city",
    "address_type",
    "additional_name",
    "local_consultant",
)


# Configure native Windows GDI functions.
gdi = ctypes.WinDLL("gdi32", use_last_error=True)

PTR = ctypes.c_void_p
INT = ctypes.c_int
DWORD = ctypes.c_uint32


def configure_gdi(name, result, arguments):
    function = getattr(gdi, name)
    function.restype = result
    function.argtypes = arguments

    return function


create_dc = configure_gdi(
    "CreateCompatibleDC", PTR, [PTR]
)

create_bitmap = configure_gdi(
    "CreateDIBSection",
    PTR,
    [PTR, PTR, DWORD, ctypes.POINTER(PTR), PTR, DWORD]
)

select_object = configure_gdi(
    "SelectObject", PTR, [PTR, PTR]
)

bitblt = configure_gdi(
    "BitBlt",
    INT,
    [PTR, INT, INT, INT, INT, PTR, INT, INT, DWORD]
)

gdi_flush = configure_gdi("GdiFlush", INT, [])

delete_object = configure_gdi(
    "DeleteObject", INT, [PTR]
)

delete_dc = configure_gdi(
    "DeleteDC", INT, [PTR]
)


def locate_grid(dialog):
    """Locate the grid using live UI geometry."""

    search = dialog.child_window(
        title="Search:",
        control_type="Text"
    ).wrapper_object()

    ok = dialog.child_window(
        title="OK",
        control_type="Button"
    ).wrapper_object()

    candidates = [
        pane
        for pane in dialog.descendants(control_type="Pane")
        if pane.element_info.class_name == "SWT_Window0"
        and pane.is_visible()
        and pane.rectangle().top >= search.rectangle().bottom
        and pane.rectangle().bottom <= ok.rectangle().top
        and pane.rectangle().width() > 0
        and pane.rectangle().height() > 0
    ]

    if len(candidates) != 1:
        raise RuntimeError(
            "Cannot identify contact grid uniquely."
        )

    return candidates[0]


def verify_selector(dialog, grid):
    """Ensure that the target selector is still active."""

    if not win32gui.IsWindow(dialog.handle):
        raise RuntimeError("Contact selector closed.")

    if win32gui.GetForegroundWindow() != dialog.handle:
        raise RuntimeError("Contact selector lost foreground.")

    if not grid.is_visible():
        raise RuntimeError("Contact grid is not visible.")


def verify_focus(dialog, grid):
    """Prevent keyboard input outside the target grid."""

    verify_selector(dialog, grid)

    if not grid.has_keyboard_focus():
        raise RuntimeError("Contact grid lost keyboard focus.")


def capture_grid(dialog, grid):
    """
    Capture the dynamically located grid in memory.

    BitBlt is used only to detect whether results exist.
    Contact values are read through the clipboard.
    """

    verify_selector(dialog, grid)

    rect = grid.rectangle()

    width = rect.width()
    height = rect.height()

    bitmap_info = ctypes.create_string_buffer(
        struct.pack(
            "<IiiHHIIiiII",
            40,
            width,
            -height,
            1,
            32,
            0,
            width * height * 4,
            0, 0, 0, 0
        )
    )

    screen_dc = win32gui.GetDC(0)

    if not screen_dc:
        raise RuntimeError("Cannot acquire screen DC.")

    memory_dc = None
    bitmap = None
    old_object = None

    try:
        memory_dc = create_dc(screen_dc)

        if not memory_dc:
            raise RuntimeError("Cannot create memory DC.")

        pixels = PTR()

        bitmap = create_bitmap(
            screen_dc,
            bitmap_info,
            0,
            ctypes.byref(pixels),
            None,
            0
        )

        if not bitmap or not pixels.value:
            raise RuntimeError("Cannot create bitmap.")

        previous = select_object(memory_dc, bitmap)

        if not previous or previous == PTR(-1).value:
            raise RuntimeError("Cannot select bitmap.")

        old_object = previous

        if not bitblt(
            memory_dc,
            0, 0,
            width, height,
            screen_dc,
            rect.left, rect.top,
            0x00CC0020
        ):
            raise RuntimeError("Grid capture failed.")

        if not gdi_flush():
            raise RuntimeError("GDI flush failed.")

        data = ctypes.string_at(
            pixels,
            width * height * 4
        )

    finally:
        if old_object:
            select_object(memory_dc, old_object)

        if bitmap:
            delete_object(bitmap)

        if memory_dc:
            delete_dc(memory_dc)

        win32gui.ReleaseDC(0, screen_dc)

    verify_selector(dialog, grid)

    if grid.rectangle() != rect:
        raise RuntimeError("Grid moved during capture.")

    return width, height, data


def capture_stable_grid(dialog, grid):
    """Require three consecutive identical RGB observations."""

    previous = None
    consecutive = 0

    for _ in range(10):
        width, height, data = capture_grid(dialog, grid)

        signature = (
            width,
            height,
            data[0::4],
            data[1::4],
            data[2::4]
        )

        if signature == previous:
            consecutive += 1
        else:
            consecutive = 1

        if consecutive >= 3:
            return width, height, data

        previous = signature

        time.sleep(ACTION_DELAY)

    raise RuntimeError("Contact grid did not stabilize.")


def detect_grid_state(dialog, grid):
    """Distinguish empty, non-empty and unknown grid states."""

    width, height, data = capture_stable_grid(dialog, grid)

    left = width * 2 // 100
    right = width * 95 // 100

    sample_x = [
        left + (right - left) * i // 65
        for i in range(1, 65)
    ]

    def is_separator(y):
        dark = 0

        for x in sample_x:
            offset = (y * width + x) * 4

            b, g, r = data[offset:offset + 3]

            if (
                max(r, g, b) < 215
                and max(r, g, b) - min(r, g, b) <= 12
            ):
                dark += 1

        return dark / len(sample_x) >= 0.85

    # Find the column header boundary dynamically.
    header_end = None

    for y in range(height // 4):
        if is_separator(y):
            header_end = y

            while (
                header_end + 1 < height
                and is_separator(header_end + 1)
            ):
                header_end += 1

            break

    if header_end is None:
        return "UNKNOWN"

    nonwhite = 0
    total = 0
    has_body_separator = False

    for y in range(header_end + 1, height):
        start = (y * width + left) * 4
        end = (y * width + right) * 4

        line = data[start:end]

        for i in range(0, len(line), 4):
            b, g, r = line[i:i + 3]

            total += 1

            if (r, g, b) != (255, 255, 255):
                nonwhite += 1

        if is_separator(y):
            has_body_separator = True

    if total == 0:
        return "UNKNOWN"

    if nonwhite == 0:
        return "EMPTY_CANDIDATE"

    if has_body_separator:
        return "NONEMPTY_CANDIDATE"

    return "UNKNOWN"


def press_key(dialog, grid, key, ctrl=False):
    """Send native keyboard events to the verified grid."""

    verify_focus(dialog, grid)

    flags = (
        win32con.KEYEVENTF_EXTENDEDKEY
        if key in (win32con.VK_END, win32con.VK_UP)
        else 0
    )

    if ctrl:
        win32api.keybd_event(
            win32con.VK_CONTROL, 0, 0, 0
        )

    try:
        win32api.keybd_event(key, 0, flags, 0)

        win32api.keybd_event(
            key,
            0,
            flags | win32con.KEYEVENTF_KEYUP,
            0
        )

    finally:
        if ctrl:
            win32api.keybd_event(
                win32con.VK_CONTROL,
                0,
                win32con.KEYEVENTF_KEYUP,
                0
            )

    time.sleep(ACTION_DELAY)


def copy_selected_row(dialog, grid):
    """Read and validate fresh clipboard data."""

    verify_focus(dialog, grid)

    before = (
        ctypes.windll.user32.GetClipboardSequenceNumber()
    )

    press_key(dialog, grid, 0x43, ctrl=True)

    deadline = time.monotonic() + CLIPBOARD_TIMEOUT

    while time.monotonic() < deadline:
        verify_focus(dialog, grid)

        after = (
            ctypes.windll.user32.GetClipboardSequenceNumber()
        )

        if after != before:
            data = clipboard.GetData()

            if not isinstance(data, str):
                raise RuntimeError("Invalid clipboard data.")

            raw = data.rstrip("\r\n")

            fields = raw.split("\t")

            if "\n" in raw or "\r" in raw:
                raise RuntimeError("Unexpected multiple lines.")

            if len(fields) != len(FIELDS):
                raise RuntimeError("Invalid contact row structure.")

            if fields[0].strip().lower() in ("", "null"):
                raise RuntimeError("Missing customer ID.")

            return tuple(fields)

        time.sleep(0.1)

    raise RuntimeError("No fresh clipboard data.")

def click_last_visible_row(dialog, grid):
    """
    Locate and explicitly select the last visible complete row.

    The click position is calculated dynamically from the
    current grid geometry and detected row separators.
    No hardcoded screen coordinates are used.
    """

    verify_selector(dialog, grid)

    rect = grid.rectangle()

    width, height, data = capture_grid(dialog, grid)

    left = width * 2 // 100
    right = width * 95 // 100

    sample_x = [
        left + (right - left) * i // 65
        for i in range(1, 65)
    ]

    def is_separator(y):

        dark = 0

        for x in sample_x:

            offset = (y * width + x) * 4

            b, g, r = data[offset:offset + 3]

            if (
                max(r, g, b) < 215
                and max(r, g, b) - min(r, g, b) <= 12
            ):
                dark += 1

        return dark / len(sample_x) >= 0.85

    # Detect horizontal separator groups.
    groups = []

    for y in range(height):

        if is_separator(y):

            if groups and y == groups[-1][-1] + 1:
                groups[-1].append(y)
            else:
                groups.append([y])

    if len(groups) < 2:
        raise RuntimeError(
            "No complete data row detected."
        )

    # Resolve the last complete visible row.
    row_top = groups[-2][-1] + 1
    row_bottom = groups[-1][0] - 1

    if row_bottom <= row_top:
        raise RuntimeError(
            "Invalid last-row boundaries."
        )

    # Reject potentially incomplete rows below the separator.
    for y in range(groups[-1][-1] + 1, height):

        for x in sample_x:

            offset = (y * width + x) * 4

            if data[offset:offset + 3] != b"\xff\xff\xff":
                raise RuntimeError(
                    "Content detected below final separator."
                )

    # Calculate the click point using live grid geometry.
    x = rect.left + width // 10
    y = rect.top + (row_top + row_bottom) // 2

    verify_selector(dialog, grid)

    if grid.rectangle() != rect:
        raise RuntimeError(
            "Grid moved before selection."
        )

    logger.info("Detected separators: %s", groups)

    logger.info(
        "Last row boundaries: %d - %d",
        row_top,
        row_bottom
    )

    logger.info(
        "Dynamic row selection: (%d, %d)",
        x,
        y
    )

    mouse.click(
        button="left",
        coords=(x, y)
    )

    time.sleep(ACTION_DELAY)

    verify_focus(dialog, grid)

    logger.info("Last visible row clicked successfully.")

def extract_rows_from_bottom(dialog, grid):
    """
    Extract contact rows from bottom to top.

    Explicitly click the last visible row before copying
    to avoid relying on keyboard focus as selection proof.
    """

    rows = []

    grid.set_focus()

    time.sleep(ACTION_DELAY)

    verify_focus(dialog, grid)

    # Navigate toward the last row.
    logger.info("Navigating to the last row...")

    press_key(
        dialog,
        grid,
        win32con.VK_END,
        ctrl=True
    )

    # Explicitly select the last visible complete row.
    click_last_visible_row(dialog, grid)

    logger.info("Starting reverse row extraction...")

    while True:

        current = copy_selected_row(dialog, grid)

        # Repeating the same row indicates a possible
        # upper navigation boundary.
        if rows and current == rows[-1]:

            logger.info(
                "First row repeated. Stopping extraction."
            )

            break

        # Reject unexpected navigation cycles.
        if current in rows:
            raise RuntimeError(
                "Unexpected grid navigation cycle."
            )

        rows.append(current)

        logger.info(
            "Contact row read: %s",
            current[0]
        )

        if len(rows) >= MAX_ROWS:
            raise RuntimeError(
                "Contact row safety limit reached."
            )

        # Navigate upward without using Enter.
        press_key(
            dialog,
            grid,
            win32con.VK_UP
        )

    # Restore the original top-to-bottom order.
    return [
        dict(zip(FIELDS, row))
        for row in reversed(rows)
    ]

def read_contact_rows(dialog):
    """
    Reacquire the current contact selector using its
    native Windows handle, matching the standalone test.
    """

    # Resolve the same selector using its native handle.
    hwnd = win32gui.FindWindow(
        None,
        "Select the address"
    )

    if not hwnd:
        raise RuntimeError("Selector not found.")

    if hwnd != dialog.handle:
        raise RuntimeError("Unexpected contact selector.")

    dialog = Desktop(backend="uia").window(handle=hwnd)

    dialog.wrapper_object().set_focus()

    time.sleep(ACTION_DELAY)

    # Discover the grid from the current UI tree.
    grid = locate_grid(dialog)

    logger.info("Grid found: %s", grid.rectangle())

    # Determine whether clipboard extraction is safe.
    state = detect_grid_state(dialog, grid)

    logger.info("Contact grid state: %s", state)

    if state == "EMPTY_CANDIDATE":
        return []

    if state != "NONEMPTY_CANDIDATE":
        raise RuntimeError(
            "Unknown contact grid state. Copy is unsafe."
        )

    rows = extract_rows_from_bottom(dialog, grid)

    logger.info("Contact rows extracted: %d", len(rows))

    return rows
def select_matched_contact(dialog, matched_row):
    """
    Requirement 2.3:
    Locate the previously matched contact, verify its
    complete row data, and confirm the selection.

    Reuse the tested reverse navigation without
    hardcoded screen coordinates.
    """

    target = tuple(
        matched_row[field]
        for field in FIELDS
    )

    target_id = matched_row["customer_id"]

    logger.info(
        "Selecting matched debtor: %s",
        target_id
    )

    # Reacquire the same selector through its native handle.
    hwnd = win32gui.FindWindow(
        None,
        "Select the address"
    )

    if not hwnd or hwnd != dialog.handle:
        raise RuntimeError(
            "Expected contact selector not found."
        )

    dialog = Desktop(backend="uia").window(
        handle=hwnd
    )

    dialog.wrapper_object().set_focus()

    time.sleep(ACTION_DELAY)

    grid = locate_grid(dialog)

    grid.set_focus()

    time.sleep(ACTION_DELAY)

    verify_focus(dialog, grid)

    # Reuse the successfully tested navigation strategy.
    press_key(
        dialog,
        grid,
        win32con.VK_END,
        ctrl=True
    )

    click_last_visible_row(dialog, grid)

    previous = None

    for _ in range(MAX_ROWS):

        current = copy_selected_row(dialog, grid)

        # Verify the complete row before confirming.
        if current == target:

            logger.info(
                "Matched row selection verified: %s",
                target_id
            )

            ok = dialog.child_window(
                title="OK",
                control_type="Button"
            ).wrapper_object()

            if not ok.is_visible() or not ok.is_enabled():
                raise RuntimeError(
                    "Contact selector OK button unavailable."
                )

            verify_focus(dialog, grid)

            # Confirm the verified contact.
            ok.click_input()

            # Verify that the selector has closed.
            dialog.wait_not("visible", timeout=10)

            logger.info(
                "Contact selector closed after OK."
            )

            return

        # Reject changed data for the same customer ID.
        if current[0] == target_id:
            raise RuntimeError(
                "Matched contact data changed."
            )

        # Stop if navigation reaches its upper boundary.
        if current == previous:
            break

        previous = current

        press_key(
            dialog,
            grid,
            win32con.VK_UP
        )

    raise RuntimeError(
        f"Could not select matched debtor: {target_id}"
    )

def cancel_contact_selector(dialog):
    """
    Requirement 2.3:
    Close the contact selector when no exact or
    conflicting debtor has been found.
    """

    hwnd = dialog.handle

    if not win32gui.IsWindow(hwnd):
        raise RuntimeError(
            "Contact selector is no longer available."
        )

    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError(
            "Contact selector lost foreground."
        )

    cancel = dialog.child_window(
        title="Cancel",
        control_type="Button"
    ).wrapper_object()

    if not cancel.is_visible() or not cancel.is_enabled():
        raise RuntimeError(
            "Cancel button unavailable."
        )

    logger.info("Cancelling contact selector...")

    cancel.click_input()

    dialog.wait_not("visible", timeout=10)

    logger.info(
        "Contact selector closed after Cancel."
    )