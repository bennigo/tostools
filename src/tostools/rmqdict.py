"""
RMQ Dictionary utilities for tostools.

This module provides utilities for creating RMQ (RabbitMQ) dictionary structures
for GPS station monitoring and quality control.
"""

from datetime import datetime


def create_station_dict(station_identifier):
    """Create a basic station dictionary structure for RMQ."""
    station = {}
    station["station_identifier"] = station_identifier
    station["sensor_location"] = "metadata"
    station["sensor_identifier"] = "gps"
    station["observation_time"] = datetime.now()
    station["monitoring"] = {"passed": [], "caught": []}
    return station


def create_monitoring_conflict_dict(arrival):
    """Create a monitoring conflict dictionary."""
    return {
        "monitoring.quality.gps.metadata.consistency.rinex_tos_conflict": {
            "severity": "critical",
            "max_observation_time": (
                arrival[1]
                if isinstance(arrival, (list, tuple)) and len(arrival) > 1
                else None
            ),
        }
    }
