"""Errors raised by the StreamLine device client."""


class StreamLineApiError(Exception):
    """The device rejected a request or returned an invalid response."""


class StreamLineAuthenticationError(StreamLineApiError):
    """The device rejected the admin key."""


class StreamLineCannotConnect(StreamLineApiError):
    """The device could not be reached."""
