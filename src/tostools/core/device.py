"""
GPS device management and session processing.

This module provides functions for managing GPS device configurations,
sessions, and device-specific queries like radome and monument information.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from ..utils.logging import get_logger


def get_device_attribute_history(device: Dict[str, Any], 
                               session_start: datetime,
                               session_end: datetime,
                               loglevel: int = logging.INFO) -> List[Dict[str, Any]]:
    """
    Get device attribute history for a given session period.
    
    Args:
        device: Device information dictionary
        session_start: Session start time
        session_end: Session end time
        loglevel: Logging level
        
    Returns:
        List of device history entries
    """
    logger = get_logger(__name__, loglevel)
    
    history = []
    
    # Process device attributes that fall within the session period
    for attr_key, attr_value in device.items():
        if isinstance(attr_value, dict) and "time_from" in attr_value:
            attr_start = attr_value.get("time_from")
            attr_end = attr_value.get("time_to")
            
            # Check if attribute period overlaps with session period
            if attr_start and (not attr_end or attr_end >= session_start):
                if attr_start <= session_end:
                    history.append({
                        "attribute": attr_key,
                        "value": attr_value,
                        "time_from": attr_start,
                        "time_to": attr_end
                    })
    
    logger.debug(f"Found {len(history)} device attributes for session")
    return history


def get_radome_info(device_history: List[Dict[str, Any]], 
                   date_from: datetime, 
                   date_to: datetime,
                   loglevel: int = logging.WARNING) -> Tuple[str, str]:
    """
    Get radome information for a given time interval.
    
    Args:
        device_history: List of device sessions
        date_from: Start date
        date_to: End date
        loglevel: Logging level
        
    Returns:
        Tuple of (radome_model, radome_serial)
    """
    logger = get_logger(__name__, loglevel)
    
    # Default radome is NONE
    radome_model = "NONE"
    radome_serial = ""
    
    for session in device_history:
        session_start = session.get("time_from")
        session_end = session.get("time_to")
        
        if not session_start:
            continue
        
        # Check if dates overlap with session
        if session_end is None or (date_from <= session_end and date_to >= session_start):
            radome_info = session.get("radome", {})
            if radome_info:
                radome_model = radome_info.get("model", "NONE")
                radome_serial = radome_info.get("serial_number", "")
                logger.debug(f"Found radome: {radome_model}, serial: {radome_serial}")
                break
    
    return radome_model, radome_serial


def get_monument_height_info(device_history: List[Dict[str, Any]], 
                            date_from: datetime, 
                            date_to: datetime,
                            loglevel: int = logging.WARNING) -> float:
    """
    Get monument height for a given time interval.
    
    Args:
        device_history: List of device sessions
        date_from: Start date  
        date_to: End date
        loglevel: Logging level
        
    Returns:
        Monument height in meters
    """
    logger = get_logger(__name__, loglevel)
    
    monument_height = 0.0
    
    for session in device_history:
        session_start = session.get("time_from")
        session_end = session.get("time_to")
        
        if not session_start:
            continue
            
        # Check if dates overlap with session
        if session_end is None or (date_from <= session_end and date_to >= session_start):
            monument_info = session.get("monument", {})
            if monument_info:
                monument_height = float(monument_info.get("monument_height", 0.0))
                logger.debug(f"Found monument height: {monument_height}")
                break
    
    return monument_height


def get_antenna_info(device_history: List[Dict[str, Any]], 
                    date_from: datetime, 
                    date_to: datetime,
                    loglevel: int = logging.WARNING) -> Dict[str, Any]:
    """
    Get antenna information for a given time interval.
    
    Args:
        device_history: List of device sessions
        date_from: Start date
        date_to: End date  
        loglevel: Logging level
        
    Returns:
        Antenna information dictionary
    """
    logger = get_logger(__name__, loglevel)
    
    antenna_info = {}
    
    for session in device_history:
        session_start = session.get("time_from")
        session_end = session.get("time_to")
        
        if not session_start:
            continue
            
        # Check if dates overlap with session
        if session_end is None or (date_from <= session_end and date_to >= session_start):
            antenna_data = session.get("antenna", {})
            if antenna_data:
                antenna_info = antenna_data.copy()
                logger.debug(f"Found antenna: {antenna_info.get('model', 'Unknown')}")
                break
    
    return antenna_info


def get_receiver_info(device_history: List[Dict[str, Any]], 
                     date_from: datetime, 
                     date_to: datetime,
                     loglevel: int = logging.WARNING) -> Dict[str, Any]:
    """
    Get GNSS receiver information for a given time interval.
    
    Args:
        device_history: List of device sessions
        date_from: Start date
        date_to: End date
        loglevel: Logging level
        
    Returns:
        Receiver information dictionary
    """
    logger = get_logger(__name__, loglevel)
    
    receiver_info = {}
    
    for session in device_history:
        session_start = session.get("time_from")
        session_end = session.get("time_to")
        
        if not session_start:
            continue
            
        # Check if dates overlap with session
        if session_end is None or (date_from <= session_end and date_to >= session_start):
            receiver_data = session.get("gnss_receiver", {})
            if receiver_data:
                receiver_info = receiver_data.copy()
                logger.debug(f"Found receiver: {receiver_info.get('model', 'Unknown')}")
                break
    
    return receiver_info


def process_device_sessions(sessions_data: List[Dict[str, Any]], 
                          loglevel: int = logging.WARNING) -> List[Dict[str, Any]]:
    """
    Process raw device sessions data into organized format.
    
    Args:
        sessions_data: Raw sessions data from TOS API
        loglevel: Logging level
        
    Returns:
        List of processed device sessions
    """
    logger = get_logger(__name__, loglevel)
    
    processed_sessions = []
    devices_used = ["gnss_receiver", "antenna", "radome", "monument"]
    
    for connection in sessions_data:
        # Skip zero-duration sessions
        if connection.get("time_from") == connection.get("time_to"):
            logger.debug(
                f"Skipping zero-duration session: {connection.get('time_from')}"
            )
            continue
        
        session = {
            "time_from": connection.get("time_from"),
            "time_to": connection.get("time_to")
        }
        
        # Add device information
        for device_type in devices_used:
            if device_type in connection:
                device_info = connection[device_type]
                if isinstance(device_info, dict):
                    session[device_type] = device_info
        
        processed_sessions.append(session)
    
    logger.info(f"Processed {len(processed_sessions)} device sessions")
    return processed_sessions


def validate_device_consistency(device_history: List[Dict[str, Any]], 
                              loglevel: int = logging.WARNING) -> Dict[str, List[str]]:
    """
    Validate device configuration consistency across sessions.
    
    Args:
        device_history: List of device sessions
        loglevel: Logging level
        
    Returns:
        Dictionary of validation issues by category
    """
    logger = get_logger(__name__, loglevel)
    
    issues = {
        "time_gaps": [],
        "overlaps": [],
        "missing_devices": [],
        "configuration_changes": []
    }
    
    # Sort sessions by start time
    sorted_sessions = sorted(device_history, key=lambda x: x.get("time_from") or datetime.min)
    
    for i, session in enumerate(sorted_sessions):
        # Check for missing required devices
        required_devices = ["gnss_receiver", "antenna"]
        for device in required_devices:
            if device not in session:
                issues["missing_devices"].append(
                    f"Session {i}: Missing {device} at {session.get('time_from')}"
                )
        
        # Check for time gaps/overlaps with next session
        if i < len(sorted_sessions) - 1:
            next_session = sorted_sessions[i + 1]
            current_end = session.get("time_to")
            next_start = next_session.get("time_from")
            
            if current_end and next_start:
                if current_end < next_start:
                    issues["time_gaps"].append(
                        f"Gap between sessions: {current_end} to {next_start}"
                    )
                elif current_end > next_start:
                    issues["overlaps"].append(
                        f"Overlap: session ends {current_end}, next starts {next_start}"
                    )
    
    total_issues = sum(len(issue_list) for issue_list in issues.values())
    logger.info(f"Device validation found {total_issues} issues")
    
    return issues