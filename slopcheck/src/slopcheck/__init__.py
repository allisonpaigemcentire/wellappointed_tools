"""Check prose for AI-writing patterns and AI jargon.

The checker reports a line, a column, the matched text, a category, and a
plain-language fix. Replace and cut jargon fail a run. A define term, or a
false friend, warns when its first use has no definition beside it.
"""

from slopcheck.check import check_paths, check_text
from slopcheck.load import ConfigError, load_jargon, load_rules

__version__ = "0.2.0"

__all__ = [
    "ConfigError",
    "check_paths",
    "check_text",
    "load_jargon",
    "load_rules",
    "__version__",
]
