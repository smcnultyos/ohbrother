"""Parse 32-byte Brother QL-800 status packets."""

from __future__ import annotations
from .exceptions import StatusError, TapeMismatchError

STATUS_TYPES: dict[int, str] = {
    0x00: "ready",
    0x01: "print_completed",
    0x02: "error",
    0x04: "turned_off",
    0x05: "notification",
    0x06: "phase_change",
}

# byte [8]
ERROR1_BITS: dict[int, str] = {
    0: "no_media",
    1: "end_of_media",
    2: "cutter_jam",
    3: "weak_batteries",
    4: "printer_in_use",
    5: "printer_turned_off",
    6: "high_voltage_adapter",
    7: "fan_motor_error",
}

# byte [9]
ERROR2_BITS: dict[int, str] = {
    0: "replace_media",
    1: "expansion_buffer_full",
    2: "transmission_error",
    3: "cover_open",
    4: "cancel_key",
    5: "media_cannot_be_fed",
    6: "system_error",
}

# byte [25] bit 7: two-color (black+red) tape
TWO_COLOR_TEXT_COLOR_FLAG = 0x80


def parse_status(data: bytes) -> dict:
    # Canonical header: 0x80 0x20 0x42 ("B80 B")
    if len(data) < 32 or data[0] != 0x80 or data[1] != 0x20 or data[2] != 0x42:
        return {
            "valid": False,
            "raw_hex": data.hex() if data else "",
            "errors": [],
        }

    e1 = [v for k, v in ERROR1_BITS.items() if data[8] & (1 << k)]
    e2 = [v for k, v in ERROR2_BITS.items() if data[9] & (1 << k)]

    # Bytes [3:5] are device-dependent model bytes encoded as ASCII digits
    # e.g. QL-800 → 0x34 0x38 → "48"
    model_code = chr(data[3]) + chr(data[4])

    media_type_raw = data[11]
    if media_type_raw == 0x00:
        media_type = "no_media"
    elif media_type_raw == 0x0A:
        media_type = "continuous"
    elif media_type_raw == 0x0B:
        media_type = "die_cut"
    else:
        media_type = hex(media_type_raw)

    return {
        "valid": True,
        "model_code": model_code,
        "media_width_mm": data[10],
        "media_length_mm": data[17],
        "media_type": media_type,
        "status_type": STATUS_TYPES.get(data[18], hex(data[18])),
        "phase": "printing" if data[19] == 0x01 else "receiving",
        "errors": e1 + e2,
        "tape_color": data[24],
        "text_color": data[25],
        "two_color_tape": bool(data[25] & TWO_COLOR_TEXT_COLOR_FLAG),
        "raw_hex": data.hex(),
    }


def validate_preflight(status: dict, red: bool, label: str) -> None:
    if not status.get("valid"):
        raise StatusError(["invalid status packet"], status)

    if status["errors"]:
        raise StatusError(status["errors"], status)

    if status["two_color_tape"] and not red:
        raise TapeMismatchError(
            f"Installed tape is two-color (text_color={hex(status['text_color'])}) "
            f"but red=False. Use PrintOptions(label='62red', red=True)."
        )
