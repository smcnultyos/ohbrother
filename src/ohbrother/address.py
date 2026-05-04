"""Address parsing and formatting for Brother address label reels."""

from __future__ import annotations

import usaddress

# usaddress token keys that form the street line, in order
_STREET_KEYS = [
    "AddressNumberPrefix",
    "AddressNumber",
    "AddressNumberSuffix",
    "StreetNamePreModifier",
    "StreetNamePreDirectional",
    "StreetNamePreType",
    "StreetName",
    "StreetNamePostType",
    "StreetNamePostDirectional",
    "OccupancyType",
    "OccupancyIdentifier",
]

_CITY_STATE_ZIP_KEYS = [
    "PlaceName",
    "StateName",
    "ZipCode",
]


def _title(token: str) -> str:
    """Title-case a token; uppercase if it looks like a state abbreviation."""
    if len(token) <= 2 and token.isalpha():
        return token.upper()
    return token.title()


def format_address(raw: str) -> str:
    """Parse and format an unstructured address string for label printing.

    Returns a 2–3 line string:
        Recipient (if present)
        Street address [+ occupancy]
        City, State ZIP

    Raises ValueError if the input cannot be classified as a street address.
    """
    try:
        tagged, addr_type = usaddress.tag(raw)
    except usaddress.RepeatedLabelError as e:
        raise ValueError(f"Ambiguous address: {raw!r}") from e

    if addr_type != "Street Address":
        raise ValueError(
            f"Could not parse {raw!r} as a street address (got type {addr_type!r})"
        )

    recipient_parts = [v for k, v in tagged.items() if k == "Recipient"]
    street_parts = [_title(v) for k, v in tagged.items() if k in _STREET_KEYS]

    city = _title(tagged.get("PlaceName", "")) if "PlaceName" in tagged else None
    state = _title(tagged.get("StateName", "")) if "StateName" in tagged else None
    zipcode = tagged.get("ZipCode") if "ZipCode" in tagged else None

    city_state_zip_parts = [p for p in [city, state, zipcode] if p]
    city_state_zip = " ".join(city_state_zip_parts)

    lines = []
    if recipient_parts:
        lines.append(_title(" ".join(recipient_parts)))
    if street_parts:
        lines.append(" ".join(street_parts))
    if city_state_zip:
        lines.append(city_state_zip)

    return "\n".join(lines)


def looks_like_address(raw: str) -> bool:
    """Return True if raw looks like a street address, False otherwise.

    Never raises.
    """
    try:
        tagged, addr_type = usaddress.tag(raw)
    except Exception:
        return False
    return addr_type == "Street Address" and "AddressNumber" in tagged
