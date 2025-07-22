# clab_connector/utils/exceptions.py


class ClabConnectorError(Exception):
    """
    Base exception for all clab-connector errors.
    """


class EDAConnectionError(ClabConnectorError):
    """
    Raised when the EDA client cannot connect or authenticate.
    """


class TopologyFileError(ClabConnectorError):
    """Raised when a topology file is missing or invalid."""
