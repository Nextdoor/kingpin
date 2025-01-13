class KingpinException(Exception):
    """Base Exception"""


class InvalidScript(KingpinException):
    """Raised when an invalid script schema was detected"""


class InvalidScriptName(KingpinException):
    """Raised when the script name does not end on .yaml or .json"""
