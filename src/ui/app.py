import logging
from pathlib import Path
from pywinauto.application import Application

logger = logging.getLogger(__name__)


class FakturamaApp:
    """Manages the connection to Fakturama using UI Automation."""

    def __init__(self):
        logger.info("Connecting to Fakturama...")

        self.app = Application(backend="uia").connect(
            title_re=r"^Fakturama - .*"
        )

        self.main_window = self.app.window(
            title_re=r"^Fakturama - .*"
        )

        self.main_window.wait("ready", timeout=10)

        logger.info("Connected to Fakturama successfully.")

    def inspect_ui(self, filename="logs/ui_inspection.txt"):
        """Save the UI control tree for development purposes."""

        Path("logs").mkdir(exist_ok=True)

        self.main_window.print_control_identifiers(
            filename=filename
        )

if __name__ == "__main__":
    FakturamaApp().inspect_ui()