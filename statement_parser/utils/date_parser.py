from datetime import datetime
from typing import Literal

# DMY formats — used by India, UK, UAE, Singapore, most of the world
_DMY_FORMATS = [
    "%d/%m/%Y", "%d/%m/%y",
    "%d-%m-%Y", "%d-%m-%y",
    "%d %b %Y", "%d-%b-%Y", "%d %b %y",
    "%d %B %Y",
    "%d.%m.%Y",
]

# MDY formats — used by US banks (Chase, BoA, Wells Fargo, Amex)
_MDY_FORMATS = [
    "%m/%d/%Y", "%m/%d/%y",
    "%m-%d-%Y",
    "%b %d, %Y",      # Jan 15, 2025
    "%B %d, %Y",      # January 15, 2025
    "%b. %d, %Y",     # Jan. 15, 2025
]

# ISO and other unambiguous formats tried for every region
_ISO_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
]

DateHint = Literal["dmy", "mdy", "auto"]


def parse_date(raw: str | None, hint: DateHint = "dmy") -> str | None:
    """
    Parse a raw date string into ISO YYYY-MM-DD format.

    Args:
        raw:  Raw date string from the PDF.
        hint: "dmy" for most of world (default), "mdy" for US banks,
              "auto" tries DMY first then MDY (use only when bank is unknown).
    """
    if not raw:
        return None
    raw = raw.strip()

    if hint == "mdy":
        ordered = _ISO_FORMATS + _MDY_FORMATS
    elif hint == "auto":
        ordered = _ISO_FORMATS + _DMY_FORMATS + _MDY_FORMATS
    else:
        ordered = _ISO_FORMATS + _DMY_FORMATS

    for fmt in ordered:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
