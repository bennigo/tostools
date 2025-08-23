"""
Output formatting utilities for GPS station data.
"""

import json
from typing import Any, Dict, List

from tabulate import tabulate


def json_print(data: Dict[str, Any]) -> str:
    """
    Format data structure as pretty-printed JSON.

    Args:
        data: Data structure to format

    Returns:
        Pretty-printed JSON string
    """
    return json.dumps(data, indent=2, default=str)


def format_station_table(
    stations: List[Dict[str, Any]], sortby: str = "marker", tablefmt: str = "simple"
) -> str:
    """
    Format station list as a table.

    Args:
        stations: List of station dictionaries
        sortby: Field to sort by
        tablefmt: Table format for tabulate

    Returns:
        Formatted table string
    """
    if not stations:
        return "No stations found."

    # Sort stations by specified field
    if sortby in stations[0]:
        stations = sorted(stations, key=lambda x: x.get(sortby, ""))

    # Extract headers and values
    headers = list(stations[0].keys())
    rows = [[station.get(h, "") for h in headers] for station in stations]

    return tabulate(rows, headers=headers, tablefmt=tablefmt)


def format_device_history(
    device_history: List[Dict[str, Any]], raw_format: bool = False
) -> str:
    """
    Format device history for display.

    Args:
        device_history: List of device history entries
        raw_format: If True, use raw tabulate format

    Returns:
        Formatted device history string
    """
    if not device_history:
        return "No device history found."

    if raw_format:
        # Use fancy table format for raw output
        formatted_entries = []
        for entry in device_history:
            # Format each device session
            devices = []
            values = []

            for device_type in ["gnss_receiver", "antenna", "radome", "monument"]:
                if device_type in entry:
                    devices.append(device_type)
                    device_data = entry[device_type]
                    values.append(
                        list(device_data.values())
                        if isinstance(device_data, dict)
                        else [str(device_data)]
                    )

            formatted_entries.append((devices, values))

        result = "+" * 200 + "\\n"
        for devices, values in formatted_entries:
            result += tabulate([devices], tablefmt="plain") + "\\n"
            result += tabulate(values, tablefmt="fancy") + "\\n"
        result += "+" * 200

        return result
    else:
        # Use simple format for regular output
        headers = ["Time From", "Time To", "Device", "Details"]
        rows = []

        for entry in device_history:
            time_from = (
                entry.get("time_from", "").strftime("%Y-%m-%d %H:%M:%S")
                if entry.get("time_from")
                else "None"
            )
            time_to = (
                entry.get("time_to", "").strftime("%Y-%m-%d %H:%M:%S")
                if entry.get("time_to")
                else "None"
            )

            for device_type in ["gnss_receiver", "antenna", "radome", "monument"]:
                if device_type in entry:
                    device_data = entry[device_type]
                    details = (
                        json.dumps(device_data, default=str)
                        if isinstance(device_data, dict)
                        else str(device_data)
                    )
                    rows.append([time_from, time_to, device_type, details])

        return tabulate(rows, headers=headers, tablefmt="simple")
