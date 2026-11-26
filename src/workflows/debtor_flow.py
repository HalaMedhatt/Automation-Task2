
import logging

from pywinauto.controls.win32_controls import EditWrapper

from src.workflows.order_flow import single_control

from src.ui.grid_reader import (
    read_contact_rows,
    select_filtered_contact,
    cancel_contact_selector,
)

from src.workflows.debtor_verification import (
    read_order_identity,
    verify_order_addresses,
)


logger = logging.getLogger(__name__)


MATCH_FIELDS = (
    "company",
    "first_name",
    "last_name",
    "zip",
    "city",
)


def open_contact_selector(fakturama, editor):
    """Open and verify the existing-contact selector."""

    logger.info("Opening existing-contact selector...")

    fakturama.main_window.set_focus()

    # Locate the address icons using the Addresses label.
    addresses_label = editor.child_window(
        title="Addresses",
        control_type="Text"
    ).wrapper_object()

    icons = addresses_label.parent().children(
        control_type="Image"
    )

    if len(icons) != 2:
        raise RuntimeError("Expected exactly two address icons.")

    # Identify the upper icon using live UI geometry.
    upper, lower = sorted(
        icons,
        key=lambda icon: icon.rectangle().top
    )

    if upper.rectangle().bottom > lower.rectangle().top:
        raise RuntimeError("Cannot distinguish address icons.")

    if not upper.is_visible() or not upper.is_enabled():
        raise RuntimeError("Contact selector icon is unavailable.")

    upper.click_input()

    # Verify that the expected dialog opened.
    dialog = fakturama.main_window.child_window(
        title="Select the address",
        control_type="Window"
    )

    dialog.wait("ready", timeout=10)

    logger.info("Contact selector opened successfully.")

    return dialog


def search_contact(dialog, query):
    """Search by company name or customer ID."""

    if not query or not query.strip():
        raise RuntimeError("Contact search query is missing.")

    logger.info("Searching for contact: %s", query)

    # Locate the search field through its label.
    search_label = dialog.child_window(
        title="Search:",
        control_type="Text"
    ).wrapper_object()

    search_field = single_control(
        search_label.parent().descendants(
            control_type="Edit"
        )
    )

    # Write using UIA and verify through Win32.
    search_field.set_edit_text(query)

    actual = EditWrapper(search_field.handle).window_text()

    if actual != query:
        raise RuntimeError("Contact search verification failed.")

    logger.info("Contact search input verified.")

    return search_field


def normalize_value(value):
    """Normalize whitespace and missing contact values."""

    if value is None:
        return None

    if not isinstance(value, str):
        raise RuntimeError(
            "Contact matching values must be strings."
        )

    value = value.strip()

    if not value or value.lower() == "null":
        return None

    return value


def is_exact_debtor_match(row, extracted):
    """
    Requirement 2.3:
    All five visible contact fields must match
    the extracted order data.
    """

    for field in MATCH_FIELDS:

        actual = normalize_value(row[field])
        expected = normalize_value(extracted[field])

        if actual is None or expected is None:
            return False

        if actual != expected:
            return False

    return True


def find_exact_debtor(rows, extracted):
    """
    Requirement 2.3:
    Evaluate all search results using the five exact
    matching fields.

    Zero matches: create a new debtor.
    One match: select the existing debtor.
    Multiple matches: stop for manual review.
    """

    # Validate required matching fields.
    for field in MATCH_FIELDS:
        if normalize_value(extracted.get(field)) is None:
            raise RuntimeError(
                f"Missing extracted debtor field: {field}"
            )

    # Collect only exact matches.
    matches = [
        row for row in rows
        if is_exact_debtor_match(row, extracted)
    ]

    logger.info("Total search results: %d", len(rows))
    logger.info("Exact matches count: %d", len(matches))

    logger.info(
        "Matching customer IDs: %s",
        [row["customer_id"] for row in matches]
    )

    # Multiple exact matches are ambiguous.
    if len(matches) > 1:
        raise RuntimeError(
            "Multiple exact debtor matches. "
            "Manual review required."
        )

    # No exact match, including an empty grid.
    if not matches:
        return None

    # Exactly one matching debtor.
    return matches[0]


def find_debtor_by_company(dialog, extracted):
    """
    Requirements 2.2 and 2.3:
    Search by company, read all results, and return
    the unique debtor matching the five required fields.

    This function does not select or confirm a contact.
    """

    company = extracted["company"]

    search_field = search_contact(dialog, company)

    # Wait for stable results and read all contact rows.
    rows = read_contact_rows(dialog)

    logger.info("Search results collected: %d", len(rows))

    # Ensure the search query remained unchanged
    # during row extraction.
    actual_search = EditWrapper(
        search_field.handle
    ).window_text()

    if actual_search != company:
        raise RuntimeError(
            "Company search changed during extraction."
        )

    logger.info("Starting exact debtor matching...")

    return find_exact_debtor(rows, extracted)


def select_contact_by_id(dialog, customer_id, expected_fields):
    """
    Search and select a known Customer ID.

    Shared by existing debtor selection (2.3)
    and newly created debtor selection (2.12).
    """

    logger.info(
        "Selecting contact by ID: %s",
        customer_id
    )

    # Narrow the search to the known customer ID.
    search_contact(dialog, customer_id)

    # Reuse direct row selection and verification.
    return select_filtered_contact(
        dialog,
        customer_id,
        expected_fields
    )


def resolve_debtor(fakturama, editor, order_data):
    """
    Execute requirements 2.1–2.4.

    Find an existing debtor by company, select the
    exact match by ID, and verify both Order addresses.

    If no exact match exists, continue to debtor creation.
    """

    logger.info("Starting debtor resolution...")

    # Preserve the original Order identity before
    # opening the modal contact selector.
    order_identity = read_order_identity(editor)

    if order_identity[1] != order_data.external_reference:
        raise RuntimeError(
            "Original Order reference does not match source data."
        )

    logger.info(
        "Original Order identity captured: %s | %s",
        *order_identity
    )

    # 2.1 Open the existing-contact selector.
    dialog = open_contact_selector(fakturama, editor)

    # Prepare the five required matching fields.
    debtor = order_data.debtor.model_dump()

    billing = debtor["billing_address"]

    extracted = {
        "company": debtor["company"],
        "first_name": debtor["first_name"],
        "last_name": debtor["last_name"],
        "zip": billing["zip_code"],
        "city": billing["city"],
    }

    # 2.2–2.3 Search by company and identify the exact match.
    matched_debtor = find_debtor_by_company(
        dialog,
        extracted
    )

    # Branch 1: No exact match.
    if matched_debtor is None:

        logger.info("Debtor decision: CREATE_NEW")

        cancel_contact_selector(dialog)

        logger.info(
            "Ready to continue with debtor creation."
        )

        return None

    # Branch 2: Exactly one match.
    logger.info("Debtor decision: SELECT_EXISTING")

    # Select directly using the verified Customer ID.
    select_contact_by_id(
        dialog,
        matched_debtor["customer_id"],
        matched_debtor
    )

    # 2.4 Verify both populated addresses
    # on the original Order.
    verify_order_addresses(
        fakturama,
        order_data,
        order_identity
    )

    logger.info("Requirement 2.4 completed successfully.")

    return matched_debtor
