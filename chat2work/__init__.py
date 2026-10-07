"""Chat2Work Core: suggest, cite, review. Never execute."""
from .engine import analyze
from .models import Analysis, Message

__all__ = ["analyze", "Analysis", "Message"]
__version__ = "0.1.2"
