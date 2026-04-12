from __future__ import annotations

import usb.core
import usb.util

BROTHER_VENDOR = 0x04F9

KNOWN_QL_PIDS: dict[int, tuple[str, str]] = {
    0x2015: ("QL-500",    ""),
    0x2016: ("QL-550",    ""),
    0x2027: ("QL-560",    ""),
    0x2028: ("QL-570",    ""),
    0x2022: ("QL-580N",   ""),
    0x201B: ("QL-650TD",  ""),
    0x2042: ("QL-700",    ""),
    0x2020: ("QL-710W",   ""),
    0x2021: ("QL-720NW",  ""),
    0x209B: ("QL-800",    "printer mode — Editor Lite off"),
    0x209E: ("QL-800",    "storage mode — disable Editor Lite: hold button until green LED off"),
    0x209F: ("QL-810W",   ""),
    0x20A0: ("QL-820NWB", ""),
    0x20C0: ("QL-1100",   ""),
    0x20C1: ("QL-1110NWB",""),
}


def discover() -> list[dict]:
    """Return connected Brother QL printers as a list of dicts.

    Keys: identifier, model, pid, serial, notes, usable.
    usable is False for PID 0x209e (Editor Lite / storage mode).
    """
    results = []
    devices = usb.core.find(find_all=True, idVendor=BROTHER_VENDOR)
    if devices is None:
        return results

    for dev in devices:
        pid = dev.idProduct
        if pid not in KNOWN_QL_PIDS:
            continue

        model, notes = KNOWN_QL_PIDS[pid]
        serial = ""
        try:
            serial = usb.util.get_string(dev, dev.iSerialNumber) or ""
        except Exception:
            pass

        identifier = f"usb://0x{BROTHER_VENDOR:04x}:0x{pid:04x}"
        if serial:
            identifier += f"/{serial}"

        results.append({
            "identifier": identifier,
            "model": model,
            "pid": hex(pid),
            "serial": serial,
            "notes": notes,
            "usable": pid != 0x209E,
        })

    return results
