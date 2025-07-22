# clab_connector/utils/logging_config.py

import logging.config
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str | None = None):
    """
    Set up logging configuration with optional file output.

    Parameters
    ----------
    log_level : str
        Desired logging level (e.g. "WARNING", "INFO", "DEBUG").
    log_file : str | None
        Path to the log file. If ``None``, logs are not written to a file.

    Returns
    -------
    None
    """
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": "%(message)s",
            },
            "file": {
                "format": "%(asctime)s %(levelname)-8s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "rich.logging.RichHandler",
                "level": log_level,
                "formatter": "console",
                "rich_tracebacks": True,
                "show_path": True,
                "markup": True,
                "log_time_format": "[%X]",
            },
        },
        "loggers": {
            "": {  # Root logger
                "handlers": ["console"],
                "level": log_level,
            },
        },
    }

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logging_config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": str(log_path),
            "level": log_level,
            "formatter": "file",
        }
        logging_config["loggers"][""]["handlers"].append("file")

    logging.config.dictConfig(logging_config)

    # Reduce verbosity from lower-level clients when using INFO level
    if logging.getLevelName(log_level) == "INFO":
        # Apply to entire clients package to catch any submodules
        logging.getLogger("clab_connector.clients").setLevel(logging.WARNING)
