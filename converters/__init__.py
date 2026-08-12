"""Universal document converter: format router + pluggable engines."""

from .registry import Format
from .router import ConvertOutcome, Router, router

__all__ = ["Format", "Router", "ConvertOutcome", "router"]
