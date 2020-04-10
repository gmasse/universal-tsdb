# vim: ai:ts=4:sw=4:sts=4:expandtab:textwidth=100:colorcolumn=+0

"""Exceptions"""

from requests import RequestException

class MaxErrorsException(RequestException):
    """Requests' Exception that means no more retry will be executed"""
