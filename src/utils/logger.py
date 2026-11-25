import logging
import os

def setup_logger():
    """Configures the global logger to output to console and a log file."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "pipeline.log")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Prevent adding handlers multiple times if imported in multiple files
    if logger.hasHandlers():
        return

    # File Handler (Saves everything with timestamp)
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_format = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s')
    file_handler.setFormatter(file_format)

    # Console Handler (Prints to terminal)
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)