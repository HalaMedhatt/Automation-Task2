
import logging

import win32gui

from src.workflows.order_flow import (
    get_order_editor,
    single_control,
)
from src.workflows.debtor_verification import (
    read_order_identity,
    select_address_tab,
)

from pywinauto.controls.win32_controls import (
    EditWrapper,
    ComboBoxWrapper,
    ButtonWrapper,
)

from pywinauto.timings import (
    wait_until,
    wait_until_passes,
)
logger = logging.getLogger(__name__)

ADDRESS_ROLES = (
    "Invoice addr.",
    "Delivery addr.",
)

def get_order_tab(app):
    """Locate the unique open Order tab."""

    tabs = [
        tab
        for tab in app.descendants(control_type="TabItem")
        if tab.element_info.name in ("New Order", "*New Order")
        and tab.is_visible()
    ]

    return single_control(tabs)


def open_new_debtor_editor(fakturama, order_identity):
    """
    Requirement 2.5:
    Open New Contact while keeping the original Order open.
    """

    logger.info("Opening New Debtor editor...")

    app = fakturama.main_window

    # Verify the original Order before switching editors.
    order_editor = get_order_editor(fakturama)

    if read_order_identity(order_editor) != order_identity:
        raise RuntimeError("Original Order identity changed.")

    get_order_tab(app)

    # Prevent opening duplicate debtor drafts.
    existing_drafts = [
        tab
        for tab in app.descendants(control_type="TabItem")
        if tab.element_info.name in (
            "New Debtor",
            "*New Debtor",
        )
    ]

    if existing_drafts:
        raise RuntimeError("A New Debtor draft is already open.")

    if not app.is_enabled():
        raise RuntimeError("Fakturama is blocked by a dialog.")

    app.set_focus()

    # Locate New Contact inside the navigation panel.
    navigation = app.child_window(
        title="Navigation View",
        control_type="Pane"
    )

    new_contact = navigation.child_window(
        title="New Contact",
        control_type="Text"
    ).wrapper_object()

    if not new_contact.is_visible() or not new_contact.is_enabled():
        raise RuntimeError("New Contact is unavailable.")

    # Verify the live click target using its current bounds.
    center = new_contact.rectangle().mid_point()

    if (
        not new_contact.handle
        or win32gui.GetForegroundWindow() != app.handle
        or win32gui.WindowFromPoint(
            (center.x, center.y)
        ) != new_contact.handle
    ):
        raise RuntimeError("New Contact click target is invalid.")

    new_contact.click_input()

    # Wait for the new debtor editor.
    editor = app.child_window(
        title="New Debtor",
        control_type="Pane"
    )

    editor.wait("ready", timeout=10)

    # Ensure the Order tab remains open.
    get_order_tab(app)

    logger.info("New Debtor editor opened successfully.")
    logger.info("Original Order tab remains open.")

    return editor


def read_customer_id(editor):
    """Read Fakturama's generated Customer ID without changing it."""

    field = editor.child_window(
        title="Customer ID",
        control_type="Edit"
    ).wrapper_object()

    customer_id = field.get_value()

    if not isinstance(customer_id, str) or not customer_id.strip():
        raise RuntimeError("Generated Customer ID is unavailable.")

    return customer_id.strip()


def resolve_edit_pair(editor, label_name):
    """
    Resolve two unnamed Edit controls using their shared
    label and current UI geometry.

    Reusable for First Name / Last Name and ZIP / City.
    """

    label = editor.child_window(
        title=label_name,
        control_type="Text"
    ).wrapper_object()

    pairs = []

    # Search only inside the shared label parent.
    for pane in label.parent().children(control_type="Pane"):

        if not pane.is_visible():
            continue

        edits = [
            field
            for field in pane.children(control_type="Edit")
            if not field.element_info.name
        ]

        if len(edits) == 2:
            pairs.append(edits)

    if len(pairs) != 1:
        raise RuntimeError(
            f"Cannot uniquely resolve fields: {label_name}"
        )

    first, second = sorted(
        pairs[0],
        key=lambda field: field.rectangle().left
    )

    if not all(
        field.is_visible() and field.is_enabled()
        for field in (first, second)
    ):
        raise RuntimeError(
            f"Fields unavailable: {label_name}"
        )

    # Verify the left-to-right relationship at runtime.
    label_bounds = label.rectangle()
    left = first.rectangle()
    right = second.rectangle()

    row_y = label_bounds.mid_point().y

    if not (
        label_bounds.right <= left.left
        < left.right <= right.left < right.right
        and max(left.top, right.top)
        <= row_y < min(left.bottom, right.bottom)
    ):
        raise RuntimeError(
            f"Cannot distinguish fields: {label_name}"
        )

    return first, second


def set_verified_text(field, value, name):
    """Write an Edit value and verify its readback."""

    if not isinstance(value, str):
        raise RuntimeError(f"Invalid field value: {name}")

    if not field.is_editable():
        raise RuntimeError(f"Field is not editable: {name}")

    current = field.get_value()

    # Do not overwrite unexpected existing data.
    if current not in ("", value):
        raise RuntimeError(
            f"Unexpected existing value: {name}"
        )

    if current != value:
        field.set_edit_text(value)

    if field.get_value() != value:
        raise RuntimeError(
            f"Field verification failed: {name}"
        )

    logger.info("%s verified: %s", name, value)



def commit_company(editor, value):
    """Populate Company and verify its value after leaving the field."""

    company = editor.child_window(
        title="Company",
        control_type="Edit"
    ).wrapper_object()

    anchor = editor.child_window(
        title="Customer ID",
        control_type="Edit"
    ).wrapper_object()

    # Reuse the existing verified text-entry method.
    set_verified_text(company, value, "Company")

    # Leave the field to trigger UI validation.
    anchor.set_focus()

    wait_until(
        3,
        0.1,
        anchor.has_keyboard_focus
    )

    # Verify that the complete value remains after leaving.
    actual = EditWrapper(company.handle).window_text()

    logger.info("Expected Company: %r", value)
    logger.info("Actual Company: %r", actual)

    if actual != value:
        raise RuntimeError("Company value was not committed.")

    logger.info("Company committed and verified: %s", value)


def verify_salutation(editor):
    """Preserve the default Salutation when none is supplied."""

    label = editor.child_window(
        title="Salutation",
        control_type="Text"
    ).wrapper_object()

    combo = single_control([
        control
        for control in label.parent().descendants(
            control_type="ComboBox"
        )
        if not control.element_info.name
        and control.is_visible()
    ])

    if combo.iface_value.CurrentValue != "---":
        raise RuntimeError("Expected default Salutation: ---")

    logger.info("Salutation preserved: ---")


def fill_debtor_identity(editor, debtor):
    """
    Requirement 2.6:
    Preserve Customer ID and populate the extracted
    Company, First Name, and Last Name.
    """

    logger.info("Preparing debtor identity...")

    # Preserve the generated ID before editing.
    customer_id = read_customer_id(editor)

    logger.info("Generated Customer ID: %s", customer_id)

    # Resolve the two unnamed name fields.
    first_name, last_name = resolve_edit_pair(
        editor,
        "First Name Last Name"
    )

    verify_salutation(editor)

    commit_company(editor, debtor.company)

    set_verified_text(
        first_name,
        debtor.first_name,
        "First Name"
    )

    set_verified_text(
        last_name,
        debtor.last_name,
        "Last Name"
    )

    # Verify all identity fields after completing entry.
    company = editor.child_window(
        title="Company",
        control_type="Edit"
    ).wrapper_object()

    if EditWrapper(company.handle).window_text() != debtor.company:
        raise RuntimeError("Company changed during identity entry.")

    if first_name.get_value() != debtor.first_name:
        raise RuntimeError("First Name changed during identity entry.")

    if last_name.get_value() != debtor.last_name:
        raise RuntimeError("Last Name changed during identity entry.")

    verify_salutation(editor)

    # Ensure Fakturama's proposed ID was not modified.
    if read_customer_id(editor) != customer_id:
        raise RuntimeError("Generated Customer ID changed.")

    logger.info("Customer ID preserved: %s", customer_id)
    logger.info("Preserve Customer ID and populate the extracted Company, First Name, and Last Name completed successfully.")

    return customer_id

def get_main_address(editor):
    """Locate and activate Addresses > Main address."""

    addresses_tab = editor.child_window(
        title="Addresses",
        control_type="TabItem"
    ).wrapper_object()

    select_address_tab(addresses_tab)

    addresses = editor.child_window(
        title="Addresses",
        control_type="Tab"
    )

    main_tab = addresses.child_window(
        title="Main address",
        control_type="TabItem"
    ).wrapper_object()

    select_address_tab(main_tab)

    main_address = addresses.child_window(
        title="Main address",
        control_type="Tab"
    )

    main_address.wait("ready", timeout=5)

    return main_address

def select_country(combo, country):
    """Select an exact Country option and verify its value."""

    if not country or not country.strip():
        raise RuntimeError("Source Country is missing.")

    # Use the native ComboBox discovered through UIA.
    if (
        combo.element_info.class_name != "ComboBox"
        or not combo.handle
    ):
        raise RuntimeError("Country ComboBox is unavailable.")

    native = ComboBoxWrapper(combo.handle)

    # Require exactly one matching native option.
    if native.item_texts().count(country) != 1:
        raise RuntimeError(
            f"Country option is missing or ambiguous: {country}"
        )

    # Avoid changing an already correct value.
    if combo.iface_value.CurrentValue != country:
        native.select(country)

    # Verify the displayed value through UIA.
    if combo.iface_value.CurrentValue != country:
        raise RuntimeError("Country verification failed.")

    logger.info("Country verified: %s", country)

def fill_address_fields(editor, main_address, billing):
    
    """
    Requirement 2.7-2.8:
    Populate and verify the selected address fields.

    Optional fields are written only when supplied
    by the source data.
    """

    logger.info("Preparing address fields...")

    customer_id = read_customer_id(editor)

    # Verify required address data before writing.
    required = {
        "Street": billing.street,
        "ZIP": billing.zip_code,
        "City": billing.city,
        "Country": billing.country,
    }

    for name, value in required.items():
        if not value or not value.strip():
            raise RuntimeError(
                f"Missing billing address field: {name}"
            )

   

    # Resolve the unnamed ZIP and City fields.
    zip_field, city_field = resolve_edit_pair(
        main_address,
        "ZIP - City"
    )

    country = main_address.child_window(
        title="Country",
        control_type="ComboBox"
    ).wrapper_object()

    # Resolve named Edit controls inside Main address.
    values = {
        "Street": billing.street,
        "E-Mail": billing.email,
        "Telephone": billing.phone,
        "additional name": billing.additional_name,
        "Address specification": billing.address_specification,
        "district": billing.district,
    }

    fields = []

    for name, value in values.items():

        # Leave fields unchanged when no source value exists.
        if value is None or not value.strip():
            logger.info("%s not supplied. Skipping.", name)
            continue

        field = main_address.child_window(
            title=name,
            control_type="Edit"
        ).wrapper_object()

        fields.append((field, value, name))

    fields.extend([
        (zip_field, billing.zip_code, "ZIP"),
        (city_field, billing.city, "City"),
    ])

    # Select Country before entering the address fields.
    select_country(country, billing.country)

    # Reuse the existing verified text-entry function.
    for field, value, name in fields:
        set_verified_text(field, value, name)

    # Leave the address fields to trigger any UI validation.
    anchor = editor.child_window(
        title="Customer ID",
        control_type="Edit"
    ).wrapper_object()

    anchor.set_focus()

    if not anchor.has_keyboard_focus():
        raise RuntimeError("Address focus verification failed.")

    # Recheck all supplied values after completing entry.
    for field, value, name in fields:

        actual = field.get_value()

        if actual != value:
            raise RuntimeError(
                f"Billing address verification failed: {name}"
            )

    # Ensure Country has not changed during entry.
    if country.iface_value.CurrentValue != billing.country:
        raise RuntimeError("Country changed during address entry.")

    # The generated Customer ID must remain unchanged.
    if read_customer_id(editor) != customer_id:
        raise RuntimeError("Generated Customer ID changed.")

    logger.info("Customer ID preserved: %s", customer_id)
    logger.info("Address fields verified successfully.")
    logger.info("Populate and verify the address completed successfully.")

def fill_billing_address(editor, billing):
    """Requirement 2.7: Populate the Main billing address."""

    main_address = get_main_address(editor)

    fill_address_fields(
        editor,
        main_address,
        billing
    )

    logger.info("Main billing address verified successfully.")



def addresses_are_identical(billing, delivery):
    """Compare the source addresses before creating another address."""

    if delivery is None:
        raise RuntimeError("Source delivery address is missing.")

    fields = (
        "company",
        "street",
        "zip_code",
        "city",
        "country",
        "additional_name",
        "address_specification",
        "district",
    )

    for name in fields:

        billing_value = (getattr(billing, name) or "").strip()
        delivery_value = (getattr(delivery, name) or "").strip()

        if billing_value != delivery_value:
            return False

    # Compare contact details when explicitly supplied for delivery.
    for name in ("email", "phone"):

        delivery_value = (getattr(delivery, name) or "").strip()
        billing_value = (getattr(billing, name) or "").strip()

        if delivery_value and delivery_value != billing_value:
            return False

    return True


def get_address_role_controls(address):
    """Locate the address type Edit and Button using UIA."""

    label = address.child_window(
        title="address type",
        control_type="Text"
    ).wrapper_object()

    pairs = []

    for pane in label.parent().children(control_type="Pane"):

        if not pane.is_visible():
            continue

        children = [
            control
            for control in pane.children()
            if control.is_visible()
        ]

        if (
            len(children) == 2
            and not any(
                control.element_info.name
                for control in children
            )
            and {
                control.element_info.control_type
                for control in children
            } == {"Edit", "Button"}
        ):
            pairs.append(children)

    if len(pairs) != 1:
        raise RuntimeError(
            "Cannot uniquely identify address type controls."
        )

    pair = pairs[0]

    field = single_control([
        control
        for control in pair
        if control.element_info.control_type == "Edit"
    ])

    button = single_control([
        control
        for control in pair
        if control.element_info.control_type == "Button"
    ])

    return field, button

def get_focused_role_checkboxes(app):
    """Identify the active address role popup using keyboard focus."""

    focused = []

    for pane in app.children(control_type="Pane"):

        if (
            pane.element_info.class_name != "#32770"
            or not pane.is_visible()
        ):
            continue

        focused.extend([
            control
            for control in pane.descendants(
                control_type="CheckBox"
            )
            if control.element_info.name in ADDRESS_ROLES
            and control.is_visible()
            and control.has_keyboard_focus()
        ])

    if not focused:
        return None

    anchor = single_control(focused)

    # Resolve both roles from the same active popup.
    siblings = anchor.parent().children(
        control_type="CheckBox"
    )

    return [
        single_control([
            control
            for control in siblings
            if control.element_info.name == role
            and control.is_visible()
        ])
        for role in ADDRESS_ROLES
    ]


def open_address_roles(app, address):
    """Open the role popup and resolve its native checkboxes."""

    _, button = get_address_role_controls(address)
    logger.info("Address type controls located.")

    street = address.child_window(
        title="Street",
        control_type="Edit"
    ).wrapper_object()

    # Move focus away from any previous address role popup.
    street.set_focus()

    if get_focused_role_checkboxes(app) is not None:
        raise RuntimeError("Previous address role popup is active.")

    if not button.is_visible() or not button.is_enabled():
        raise RuntimeError("Address role button is unavailable.")

    logger.info("Opening address role popup...")

    button.invoke()

    logger.info("Address role button invoked.")

    def find_checkboxes():

        checks = get_focused_role_checkboxes(app)

        if checks is None:
            raise RuntimeError("Waiting for address role popup.")

        return checks

    checks = wait_until_passes(
        3,
        0.15,
        find_checkboxes,
        RuntimeError
    )
    logger.info("Active address role popup detected.")
    native = []

    for checkbox in checks:

        if (
            checkbox.element_info.class_name != "Button"
            or not checkbox.handle
        ):
            raise RuntimeError(
                "Native address role checkbox is unavailable."
            )

        native.append(ButtonWrapper(checkbox.handle))

    return street, checks, native


def configure_address_roles(
    app,
    address,
    invoice,
    delivery,
    assign=True
):
    """Assign address roles and verify the committed value."""

    expected = [int(invoice), int(delivery)]

    required_roles = [
        role
        for role, enabled in zip(ADDRESS_ROLES, expected)
        if enabled
    ]

    if assign:

        # Open the popup only once.
        street, checks, native = open_address_roles(
            app,
            address
        )

        states = [
            button.get_check_state()
            for button in native
        ]

        if any(state not in (0, 1) for state in states):
            raise RuntimeError("Unknown address checkbox state.")

        # Change only incorrect checkbox states.
        for checkbox, current, target in zip(
            checks,
            states,
            expected
        ):
            if current != target:
                checkbox.invoke()

        actual = [
            button.get_check_state()
            for button in native
        ]

        if actual != expected:
            raise RuntimeError("Address role verification failed.")

        # Leave the popup to commit the selected roles.
        street.set_focus()

        wait_until(
            3,
            0.15,
            lambda: get_focused_role_checkboxes(app) is None
        )

    # Read the committed address type without reopening the popup.
    field, _ = get_address_role_controls(address)

    actual = field.get_value().strip()

    logger.info("Expected address roles: %s", required_roles)
    logger.info("Committed address type: %r", actual)

    # Accept only the required roles, regardless of their order
    # or supported display separators.
    valid_values = {
        separator.join(roles)
        for separator in (", ", ",", "; ", ";", " ")
        for roles in (required_roles, required_roles[::-1])
    }

    if actual not in valid_values:
        raise RuntimeError(
            "Committed address roles do not match."
        )

    logger.info(
        "Address roles verified | Invoice: %s | Delivery: %s",
        invoice,
        delivery
    )

def create_delivery_address(editor):
    """Create exactly one additional address and locate its tab."""

    main = get_main_address(editor)

    # Prevent creating duplicate additional addresses.
    existing = [
        tab
        for tab in main.children(control_type="TabItem")
        if tab.is_visible()
        and tab.element_info.name != "Main address"
    ]

    if existing:
        raise RuntimeError("An additional address already exists.")

    button = single_control([
        control
        for control in main.children(control_type="Button")
        if control.element_info.name == "+"
        and control.is_visible()
        and control.is_enabled()
    ])

    button.invoke()

    addresses = editor.child_window(
        title="Addresses",
        control_type="Tab"
    )

    def find_delivery_tab():

        tabs = [
            tab
            for tab in addresses.descendants(
                control_type="TabItem"
            )
            if tab.is_visible()
            and tab.element_info.name.startswith(
                "additional address #"
            )
        ]

        if not tabs:
            raise RuntimeError("Waiting for additional address.")

        return single_control(tabs)

    tab = wait_until_passes(
        5,
        0.15,
        find_delivery_tab,
        RuntimeError
    )

    # Use Fakturama's generated tab name.
    tab_name = tab.element_info.name

    select_address_tab(tab)

    delivery = addresses.child_window(
        title=tab_name,
        control_type="Tab"
    )

    delivery.wait("ready", timeout=5)

    logger.info("Additional address created: %s", tab_name)

    return delivery

def assign_address_roles(fakturama, editor, debtor):
    """
    Requirement 2.8:
    Assign Invoice and Delivery roles to a shared address,
    or create a separate delivery address when required.
    """

    logger.info("Starting address role assignment...")

    customer_id = read_customer_id(editor)

    app = fakturama.main_window

    billing = debtor.billing_address
    delivery = debtor.delivery_address

    shared = addresses_are_identical(
        billing,
        delivery
    )

    # Prepare separate delivery data before modifying roles.
    if not shared:

        for name in ("company", "street", "zip_code", "city", "country"):

            value = getattr(delivery, name)

            if not value or not value.strip():
                raise RuntimeError(
                    f"Missing delivery address field: {name}"
                )

        # Fakturama stores a different delivery company name
        # in the additional name field.
        additional_name = delivery.additional_name

        if delivery.company != debtor.company:

            if additional_name and additional_name != delivery.company:
                raise RuntimeError(
                    "Conflicting delivery company and additional name."
                )

            delivery = delivery.model_copy(
                update={"additional_name": delivery.company}
            )

    main = get_main_address(editor)

    existing = [
        tab
        for tab in main.children(control_type="TabItem")
        if tab.is_visible()
        and tab.element_info.name != "Main address"
    ]

    if existing:
        raise RuntimeError("Unexpected additional address exists.")

    # Main address must always have the Invoice role.
    configure_address_roles(
        app,
        main,
        invoice=True,
        delivery=shared
    )

    if shared:

        logger.info(
            "Billing and delivery are identical. "
            "No additional address required."
        )

    else:

        logger.info(
            "Billing and delivery are different. "
            "Creating separate delivery address."
        )

        delivery_editor = create_delivery_address(editor)

        # Reuse the same verified address-entry logic.
        fill_address_fields(
            editor,
            delivery_editor,
            delivery
        )

        # Assign Delivery only to the additional address.
        configure_address_roles(
            app,
            delivery_editor,
            invoice=False,
            delivery=True
        )

        # Verify that Main retained its Invoice role.
        main = get_main_address(editor)

        configure_address_roles(
            app,
            main,
            invoice=True,
            delivery=False,
            assign=False
        )

    # Ensure the generated Customer ID was not modified.
    if read_customer_id(editor) != customer_id:
        raise RuntimeError("Generated Customer ID changed.")

    logger.info("Customer ID preserved: %s", customer_id)
    logger.info("Address role assignment completed successfully.")
