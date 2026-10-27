"""Safe API error responses; never log exception payloads or connection settings."""
import logging
from django.core.exceptions import TooManyFieldsSent
from rest_framework.response import Response
from rest_framework.views import exception_handler

LOGGER = logging.getLogger(__name__)

def safe_exception_handler(exc, context):
    if isinstance(exc, TooManyFieldsSent):
        return Response({"detail": "The request contains too many fields."}, status=400)
    response = exception_handler(exc, context)
    if response is not None:
        return response
    LOGGER.error("Unhandled API exception type: %s", type(exc).__name__)
    return Response({"detail": "The lineup service could not complete this request."}, status=500)

