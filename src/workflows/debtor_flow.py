import logging

from pywinauto.controls.win32_controls import EditWrapper

from src.workflows.order_flow import single_control

from src.ui.grid_reader import (
    read_contact_rows,
    select_matched_contact,
    cancel_contact_selector,
)

logger = logging.getLogger(__name__)




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


def search_contact(dialog, company):
    """Search by the extracted company and verify the input."""

    if not company or not company.strip():
        raise RuntimeError("Extracted company name is missing.")

    logger.info("Searching for company...")

    # Locate the unnamed Edit through its Search label.
    search_label = dialog.child_window(
        title="Search:",
        control_type="Text"
    ).wrapper_object()

    search_field = single_control(
        search_label.parent().descendants(control_type="Edit")
    )

    # Write using UIA and read using the native Win32 Edit.
    search_field.set_edit_text(company)

    actual = EditWrapper(search_field.handle).window_text()

    if actual != company:
        raise RuntimeError("Company search verification failed.")

    logger.info("Company search input verified.")

    return search_field
MATCH_FIELDS = (
    "company",
    "first_name",
    "last_name",
    "zip",
    "city",
)


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

def is_conflicting_debtor(row, extracted):
    """
    Requirement 2.3:
    Detect conflicting identities without treating
    every non-exact match as a conflict.

    This function is called only for non-exact rows.
    """

    identity_fields = (
        "company",
        "first_name",
        "last_name",
    )

    # All three identity fields must be present and match.
    for field in identity_fields:

        actual = normalize_value(row[field])
        expected = normalize_value(extracted[field])

        if actual is None or expected is None:
            return False

        if actual.casefold() != expected.casefold():
            return False

    # The same debtor identity exists, but the row failed
    # exact matching due to differing or missing values.
    return True

def find_exact_debtor(rows, extracted):
    """
    Requirement 2.3:
    Evaluate all collected rows before deciding whether
    to select, stop for review, or create a debtor.
    """

    # Validate the required extracted matching fields.
    for field in MATCH_FIELDS:

        if normalize_value(extracted.get(field)) is None:
            raise RuntimeError(
                f"Missing extracted debtor field: {field}"
            )

    matches = []
    conflicts = []

    # Evaluate every collected search result.
    for row in rows:

        if is_exact_debtor_match(row, extracted):
            matches.append(row)

        elif is_conflicting_debtor(row, extracted):
            conflicts.append(row)

    # A matching customer ID with different row data
    # also requires manual review.
    matched_ids = {
        row["customer_id"]
        for row in matches
    }

    for row in rows:

        if (
            row["customer_id"] in matched_ids
            and row not in matches
            and row not in conflicts
        ):
            conflicts.append(row)

    logger.info("Total search results: %d", len(rows))
    logger.info("Exact matches count: %d", len(matches))
    logger.info("Conflicting rows count: %d", len(conflicts))

    logger.info(
        "Matching customer IDs: %s",
        [row["customer_id"] for row in matches]
    )

    logger.info(
        "Conflicting customer IDs: %s",
        [row["customer_id"] for row in conflicts]
    )

    # Multiple exact matches or conflicting identities
    # must never trigger automatic selection or creation.
    if len(matches) > 1 or conflicts:

        raise RuntimeError(
            "Conflicting or ambiguous debtor results. "
            "Manual review required."
        )

    # No exact or conflicting contact was found.
    if not matches:
        return None

    # Only one exact match and no detected conflicts.
    return matches[0]

def resolve_debtor(fakturama, editor, order_data):
    """
    Execute requirements 2.1, 2.2 and the matching
    portion of 2.3 in the required order.
    """

    logger.info("Starting debtor resolution...")

    # 2.1 Open the existing-contact selector.
    dialog = open_contact_selector(fakturama, editor)

    # Access the extracted debtor data.
    debtor = order_data.debtor.model_dump()

    # 2.2 Search using the extracted company.
    company = debtor.get("company")

    search_field = search_contact(dialog, company)

    # Wait for stable results and extract all contact rows.
    rows = read_contact_rows(dialog)

    logger.info("Search results collected: %d", len(rows))

    # Verify that the search query has not changed.
    actual_search = EditWrapper(
        search_field.handle
    ).window_text()

    if actual_search != company:
        raise RuntimeError(
            "Company search changed during extraction."
        )

    # 2.3 Map extracted debtor data to the visible grid fields.
    # Use the billing address for debtor identity matching.
    billing = debtor["billing_address"]

    extracted = {
        "company": debtor["company"],
        "first_name": debtor["first_name"],
        "last_name": debtor["last_name"],
        "zip": billing["zip_code"],
        "city": billing["city"],
    }

    logger.info("Starting exact debtor matching...")

    # Evaluate every result before interacting with the UI.
    matched_debtor = find_exact_debtor(
        rows,
        extracted
    )

    # Branch 1: No exact match and no detected conflicts.
    if matched_debtor is None:

        logger.info("Debtor decision: CREATE_NEW")

        cancel_contact_selector(dialog)

        logger.info(
            "Ready to continue with debtor creation."
        )

        return None

    # Branch 2: Exactly one match without conflicts.
    logger.info("Debtor decision: SELECT_EXISTING")

    logger.info(
        "Exact debtor match found: %s",
        matched_debtor["customer_id"]
    )

    select_matched_contact(
        dialog,
        matched_debtor
    )

    return matched_debtor