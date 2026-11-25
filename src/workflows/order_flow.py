
import re
import logging
from datetime import datetime

from pywinauto.timings import wait_until
from src.ui.app import FakturamaApp
from pywinauto.controls.win32_controls import EditWrapper

logger = logging.getLogger(__name__)


def get_order_editor(fakturama: FakturamaApp):
    """Locate the open New Order editor."""

    editor = fakturama.main_window.child_window(
        title="New Order",
        control_type="Pane"
    )

    editor.wait("ready", timeout=10)
    return editor


def open_new_order(fakturama: FakturamaApp):
    """Open and verify a new Order."""

    logger.info("Opening New Order...")

    existing_tabs = fakturama.main_window.descendants(
        control_type="TabItem"
    )

    if any(
        tab.window_text() in ("New Order", "*New Order")
        for tab in existing_tabs
    ):
        raise RuntimeError("An unsaved Order is already open.")
    
    fakturama.main_window.set_focus()

    order_button = fakturama.main_window.child_window(
        title="Create: New Order",
        control_type="Button"
    )

    order_button.wait("ready", timeout=10)
    order_button.click_input()

    editor = get_order_editor(fakturama)

    logger.info("New Order opened successfully.")

    return editor


def single_control(controls):
    """Require exactly one matching control."""

    if len(controls) != 1:
        raise RuntimeError(
            f"Expected one control, found {len(controls)}."
        )

    return controls[0]




def set_order_date(date_container, reference_field, wanted):
    """Update and verify the SWT Order Date."""

    date_format = "%b %d, %Y"

    date_field = single_control(
        date_container.children(control_type="Edit")
    )

    # Reset the active date segment if necessary.
    if date_field.has_keyboard_focus():
        reference_field.set_focus()

        if not reference_field.has_keyboard_focus():
            raise RuntimeError("Could not reset Date focus.")

    date_field.set_focus()

    if not date_field.has_keyboard_focus():
        raise RuntimeError("Could not focus Order Date.")

    current = datetime.strptime(
        date_field.get_value(), date_format
    ).date()

    logger.info("Current Order Date: %s", current)
    logger.info("Required Order Date: %s", wanted)

    # Use the dynamically discovered native Edit handle.
    if date_field.element_info.class_name != "Edit" or not date_field.handle:
        raise RuntimeError("Native Date Edit is unavailable.")

    native = EditWrapper(date_field.handle)

    pattern = re.compile(
        r"(?P<month>[A-Za-z]+) "
        r"(?P<day>[0-9]{1,2}), "
        r"(?P<year>[0-9]{4})"
    )

    def active_segment():
        """Identify the selected date segment."""

        if not date_field.has_keyboard_focus():
            raise RuntimeError("Date field lost focus.")

        match = pattern.fullmatch(date_field.get_value())

        if match:
            selection = native.selection_indices()

            for field in ("month", "day", "year"):
                if selection == match.span(field):
                    return field

        raise RuntimeError("Cannot identify active date segment.")

    def send_keys(keys):
        """Send keyboard input only to the focused Date field."""

        if not date_field.has_keyboard_focus():
            raise RuntimeError("Date field lost focus.")

        date_field.type_keys(
            keys,
            set_foreground=False,
            turn_off_numlock=False,
            vk_packet=False
        )

    def change_segment(field, value):
        nonlocal current

        # Navigate to the required calendar segment.
        for _ in range(2):
            previous = active_segment()

            if previous == field:
                break

            send_keys("{RIGHT}")

            wait_until(
                1, 0.05,
                lambda: active_segment() != previous
            )

        if active_segment() != field:
            raise RuntimeError(f"Cannot select date {field}.")

        expected = current.replace(**{field: value})

        width = 4 if field == "year" else 2
        send_keys(f"{value:0{width}d}")

        actual = datetime.strptime(
            date_field.get_value(), date_format
        ).date()

        if actual != expected:
            raise RuntimeError(f"Date {field} update failed.")

        current = actual

    # Prevent invalid dates during month or year changes.
    if current.day > 28 and (
        current.year != wanted.year
        or current.month != wanted.month
    ):
        change_segment("day", min(wanted.day, 28))

    # Update only the segments that need changing.
    for field in ("year", "month", "day"):
        value = getattr(wanted, field)

        if getattr(current, field) != value:
            change_segment(field, value)

    # Leave and re-enter the field to verify date commitment.
    reference_field.set_focus()

    if not reference_field.has_keyboard_focus():
        raise RuntimeError("Could not leave Date field.")

    date_field = single_control(
        date_container.children(control_type="Edit")
    )

    date_field.set_focus()

    if not date_field.has_keyboard_focus():
        raise RuntimeError("Could not refocus Date field.")

    actual = datetime.strptime(
        date_field.get_value(), date_format
    ).date()

    if actual != wanted:
        raise RuntimeError("Order Date did not retain its value.")

    logger.info("Order Date committed and verified: %s", actual)

    return date_field




def fill_order_header(editor, order_date, external_reference):
    """Fill and verify the required New Order fields."""

    logger.info("Preparing Order header...")

    # Resolve unnamed fields using the live UI hierarchy.
    date_label = editor.child_window(
        title="Date",
        control_type="Text"
    ).wrapper_object()

    header = date_label.parent()

    number_field = single_control(
        header.children(control_type="Edit")
    )

    date_container = single_control(
        header.children(control_type="Pane")
    )

    price_mode = single_control(
        header.children(control_type="ComboBox")
    )

    reference_field = editor.child_window(
        title="Cust.Ref.",
        control_type="Edit"
    ).wrapper_object()

    vat_mode = editor.child_window(
        title="VAT",
        control_type="ComboBox"
    ).wrapper_object()

    # 1.4 Preserve the automatically generated Order Number.
    order_number = number_field.get_value()

    if not order_number.strip():
        raise RuntimeError("Order Number is missing.")

    # 1.5 Set and verify the extracted Order Date.
    expected_date = datetime.strptime(
        str(order_date), "%Y-%m-%d"
    ).date()

    date_field = set_order_date(
        date_container,
        reference_field,
        expected_date
    )

    # 1.6 Set the External Reference.
    if reference_field.get_value() != external_reference:
        reference_field.set_edit_text(external_reference)

    # 1.7 Select the required price and VAT modes.
    if price_mode.selected_text() != "Net":
        price_mode.select("Net")

    if vat_mode.selected_text() != "With VAT":
        vat_mode.select("With VAT")

    # Verify all header values after completing the updates.
    actual_date = datetime.strptime(
        date_field.get_value(), "%b %d, %Y"
    ).date()

    if actual_date != expected_date:
        raise RuntimeError("Order Date verification failed.")

    if reference_field.get_value() != external_reference:
        raise RuntimeError("External Reference verification failed.")

    if price_mode.selected_text() != "Net":
        raise RuntimeError("Net mode verification failed.")

    if vat_mode.selected_text() != "With VAT":
        raise RuntimeError("VAT mode verification failed.")

    if number_field.get_value() != order_number:
        raise RuntimeError("Order Number changed unexpectedly.")

    logger.info("Order Number preserved: %s", order_number)
    logger.info("Order Date verified: %s", actual_date)
    logger.info("External Reference verified.")
    logger.info("Price Mode verified: Net")
    logger.info("VAT Mode verified: With VAT")
    logger.info("Order header prepared successfully.")

    
def prepare_order(fakturama, order):
    """Execute Section 1.3–1.8."""

    editor = open_new_order(fakturama)

    fill_order_header(
        editor,
        order.order_date,
        order.external_reference
    )

    return editor

