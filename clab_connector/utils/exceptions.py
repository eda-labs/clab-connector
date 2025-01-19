# clab_connector/utils/exceptions.py


class ClabConnectorError(Exception):
    """
    Base exception for all clab-connector errors.
    """

    pass


class EDAConnectionError(ClabConnectorError):
    """
    Raised when the EDA client cannot connect or authenticate.
    """

    pass
