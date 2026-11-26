
import logging

import win32gui

from comtypes import COMError
from pywinauto.timings import wait_until
from pywinauto.uia_defines import NoPatternInterfaceError

from src.workflows.order_flow import (
    get_order_editor,
    single_control,
)

logger = logging.getLogger(__name__)


def read_order_identity(editor):
    """Read the generated Order number and external reference."""

    # Reuse the existing Order header discovery strategy.
    date_label = editor.child_window(
        title="Date",
        control_type="Text"
    ).wrapper_object()

    number_field = single_control(
        date_label.parent().children(
            control_type="Edit"
        )
    )

    reference_field = editor.child_window(
        title="Cust.Ref.",
        control_type="Edit"
    ).wrapper_object()

    number = number_field.get_value()
    reference = reference_field.get_value()

    if not number or not reference:
        raise RuntimeError("Order identity is incomplete.")

    return number, reference


def select_address_tab(tab):
    """Select and verify an SWT address tab."""

    if not tab.is_visible() or not tab.is_enabled():
        raise RuntimeError("Address tab is unavailable.")

    if tab.is_selected():
        return

    # Prefer the semantic UIA SelectionItem pattern.
    try:
        tab.select()
    except (COMError, NoPatternInterfaceError):
        logger.info("UIA tab selection unavailable.")

    if not tab.is_selected():

        # SWT may reject UIA selection.
        # Use the current control bounds after a native hit test.
        parent = tab.parent()

        if (
            parent.element_info.control_type != "Tab"
            or parent.element_info.class_name != "SWT_Window0"
            or not parent.handle
        ):
            raise RuntimeError(
                "Cannot verify native address tab parent."
            )

        center = tab.rectangle().mid_point()

        if win32gui.WindowFromPoint(
            (center.x, center.y)
        ) != parent.handle:
            raise RuntimeError("Address tab hit test failed.")

        tab.click_input()

    # Verify that the requested tab is active.
    wait_until(
        5,
        0.1,
        tab.is_selected
    )


def read_order_addresses(editor):
    """Read both populated addresses from the Order."""

    logger.info("Reading populated Order addresses...")

    invoice_tab = editor.child_window(
        title="Invoice addr.",
        control_type="TabItem"
    ).wrapper_object()

    delivery_tab = editor.child_window(
        title="Delivery addr.",
        control_type="TabItem"
    ).wrapper_object()

    # Both addresses must belong to the same TabControl.
    if (
        invoice_tab.parent().element_info
        != delivery_tab.parent().element_info
    ):
        raise RuntimeError(
            "Address tabs do not share the same parent."
        )

    addresses = {}

    for name, tab in (
        ("invoice_address", invoice_tab),
        ("delivery_address", delivery_tab),
    ):
        select_address_tab(tab)

        # SWT exposes the active address through
        # an unnamed, visible Edit control.
        field = single_control([
            control
            for control in tab.parent().descendants(
                control_type="Edit"
            )
            if control.is_visible()
            and not control.element_info.name
        ])

        actual = field.get_value()

        if not isinstance(actual, str) or not actual.strip():
            raise RuntimeError(
                f"{name} is empty or unreadable."
            )

        addresses[name] = actual

        logger.info("%s read successfully.", name)

    # Restore the Invoice address tab.
    select_address_tab(invoice_tab)

    return addresses


def normalize_address(value):
    """Normalize display whitespace and letter casing."""

    return tuple(
        " ".join(line.split()).casefold()
        for line in value.splitlines()
        if line.strip()
    )


def verify_displayed_address(
    actual,
    debtor,
    address,
    label
):
    """Compare the displayed address with extracted data."""

    full_name = " ".join(
        filter(None, (
            debtor.first_name,
            debtor.last_name,
        ))
    )

    locality = f"{address.zip_code} {address.city}"

    # Fakturama displays the debtor's main company name
    # in Order addresses instead of the additional address name.
    prefix = [
        debtor.company,
        full_name,
        address.street,
    ]

    expected = "\n".join(
        line for line in [
            *prefix,
            locality,
            address.country,
        ]
        if line
    )

    valid_formats = {
        normalize_address(expected)
    }

    # Fakturama may prefix German postal codes with DE-.
    # Accept formatting differences, not changed ZIP values.
    if address.country.strip().casefold() == "germany":

        german_format = "\n".join(
            line for line in [
                *prefix,
                f"DE-{locality}",
                address.country,
            ]
            if line
        )

        valid_formats.add(
            normalize_address(german_format)
        )

    if normalize_address(actual) not in valid_formats:

        logger.error("%s address mismatch.", label)
        logger.error("Expected:\n%s", expected)
        logger.error("Actual:\n%s", actual)

        raise RuntimeError(
            f"{label} address does not match source data."
        )

    logger.info(
        "%s address verified successfully.",
        label
    )


def verify_order_addresses(
    fakturama,
    order_data,
    expected_identity
):
    """
    Requirements 2.4 and 2.13:
    Verify both populated addresses on the original Order.
    """

    logger.info("Starting Order address verification...")

    editor = get_order_editor(fakturama)

    if read_order_identity(editor) != expected_identity:
        raise RuntimeError("Original Order identity changed.")

    addresses = read_order_addresses(editor)

    debtor = order_data.debtor

    verify_displayed_address(
        addresses["invoice_address"],
        debtor,
        debtor.billing_address,
        "Invoice"
    )

    verify_displayed_address(
        addresses["delivery_address"],
        debtor,
        debtor.delivery_address,
        "Delivery"
    )

    # Ensure the same Order remains open after verification.
    editor = get_order_editor(fakturama)

    if read_order_identity(editor) != expected_identity:
        raise RuntimeError(
            "Order identity changed during verification."
        )

    logger.info("Original Order identity preserved.")
    logger.info("Both Order addresses verified successfully.")

    return addresses
