import argparse
import logging
from pathlib import Path

from src.utils.logger import setup_logger
from src.extraction.gemini_client import extract_order_from_image
from src.models.order import OrderData
from src.models.validation import validate_order_totals, DataValidationError
from src.ui.app import FakturamaApp
from src.workflows.order_flow import prepare_order
from src.workflows.debtor_flow import resolve_debtor

def main():
    # Initialize logging.
    setup_logger()
    logger = logging.getLogger(__name__)

    # Configure the pipeline input mode.
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-json",
        action="store_true",
        help="Load previously extracted order data without calling Gemini."
    )
    args = parser.parse_args()

    image_path = "data/input/order.png"
    json_path = Path("data/output/order.json")

    logger.info("Starting the Image-to-Cash Automation pipeline...")

    try:
        # Step 1: Extract from Gemini or load saved JSON.
        if args.from_json:
            logger.info("Loading order data from JSON...")

            order_data = OrderData.model_validate_json(
                json_path.read_text(encoding="utf-8")
            )
        else:
            order_data = extract_order_from_image(image_path)

        # Step 2: Validate the order regardless of its source.
        validate_order_totals(order_data)

        # Step 3: Save successfully extracted and validated data.
        if not args.from_json:
            json_path.parent.mkdir(parents=True, exist_ok=True)

            json_path.write_text(
                order_data.model_dump_json(indent=4),
                encoding="utf-8"
            )

            logger.info("Order data saved to %s", json_path)

        # Step 4: Log the validated order summary.
        logger.info("--- Validated Order Data ---")
        logger.info(
            "Ref: %s | Date: %s",
            order_data.external_reference,
            order_data.order_date
        )

        logger.info("Items:")

        for item in order_data.items:
            logger.info(
                "SKU: %s | Qty: %s | Net: %s | Disc: %s%% | VAT: %s%%",
                item.sku,
                item.quantity,
                item.unit_net_price,
                item.discount,
                item.vat_percentage
            )

        logger.info(
            "Totals -> Net: %s | VAT: %s | Gross: %s",
            order_data.total_net,
            order_data.total_vat,
            order_data.total_gross
        )

        # Step 5: Connect to Fakturama using UI Automation.
        fakturama = FakturamaApp()

        # Step 6: Open, prepare and verify the New Order.
        editor = prepare_order(fakturama, order_data)

        logger.info("Section 1 completed successfully.")

        # Step 7: Search, read and match the debtor.
        matched_debtor = resolve_debtor(
            fakturama,
            editor,
            order_data
        )

        if matched_debtor is not None:
            logger.info(
                "Matched debtor ID: %s",
                matched_debtor["customer_id"]
            )
        else:
            logger.info(
                "No exact match. Debtor selection or creation pending."
            )

        logger.info("Debtor matching stage completed.")

        return 0

    except DataValidationError as e:
        logger.error("Validation failed: %s", e)
        return 1

    except RuntimeError as e:
        logger.error("Pipeline stopped: %s", e)
        return 1

    except Exception as e:
        logger.error(
            "Unexpected pipeline error: %s",
            type(e).__name__
        )
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
