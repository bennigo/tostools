"""
TOS (Technical Operations System) API client.

This module provides functions to interact with the TOS REST API for GPS station
metadata retrieval and management.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

import requests

from ..utils.logging import get_logger

# TOS API Configuration
DEFAULT_TOS_URL = "https://vi-api.vedur.is:11223/tos/v1"
DEFAULT_TIMEOUT = 10


class TOSClient:
    """Client for interacting with TOS API."""
    
    def __init__(self, 
                 base_url: str = DEFAULT_TOS_URL,
                 timeout: int = DEFAULT_TIMEOUT,
                 loglevel: int = logging.WARNING):
        """
        Initialize TOS client.
        
        Args:
            base_url: Base URL for TOS API
            timeout: Request timeout in seconds
            loglevel: Logging level
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.logger = get_logger(__name__, loglevel)
    
    def _make_request(self, 
                     endpoint: str,
                     method: str = "GET",
                     data: Optional[Dict] = None,
                     params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make HTTP request to TOS API.
        
        Args:
            endpoint: API endpoint (without base URL)
            method: HTTP method
            data: Request body data
            params: URL parameters
            
        Returns:
            Response data as dictionary, or None if error
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        self.logger.info(f"Sending request \"{url}\"")
        
        try:
            if method.upper() == "POST":
                response = requests.post(url, json=data, params=params, timeout=self.timeout)
            else:
                response = requests.get(url, params=params, timeout=self.timeout)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
            return None
        except ValueError as e:
            self.logger.error(f"Invalid JSON response: {e}")
            return None
    
    def search_stations(self,
                       station_identifier: str,
                       code: str = "marker",
                       domains: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for stations in TOS database.
        
        Args:
            station_identifier: Station identifier to search for
            code: Search code type (marker, name, etc.)
            domains: Domain filter (e.g., "geophysical")
            
        Returns:
            List of matching stations
        """
        # Try different search strategies
        search_data = {
            "filters": [
                {
                    "name": code,
                    "op": "ilike",
                    "val": f"%{station_identifier}%"
                }
            ]
        }
        
        domain_path = f"/station/{domains}/" if domains else "/station/"
        endpoint = f"entity/search{domain_path}"
        
        result = self._make_request(endpoint, method="POST", data=search_data)
        
        if result and "objects" in result:
            stations = result["objects"]
            self.logger.info(f"Found {len(stations)} stations matching '{station_identifier}'")
            return stations
        else:
            self.logger.warning(f"No stations found matching '{station_identifier}'")
            return []
    
    def get_station_metadata(self, station_identifier: str, domains: str = "geophysical") -> tuple[Optional[Dict], Optional[Dict]]:
        """
        Get complete station metadata including device history.
        
        Args:
            station_identifier: Station identifier
            domains: Domain filter
            
        Returns:
            Tuple of (station_data, device_history) or (None, None) if not found
        """
        stations = self.search_stations(station_identifier, domains=domains)
        
        if not stations:
            return None, None
        
        station = stations[0]
        station_id = station["id_entity"]
        
        self.logger.info(f"station {station_identifier} id_entity: {station_id}")
        
        # Get device history
        device_history = self._make_request(f"history/entity/{station_id}/")
        
        if device_history:
            return station, device_history
        else:
            return station, None
    
    def get_contacts(self, entity_id: int) -> List[Dict[str, Any]]:
        """
        Get contact information for an entity.
        
        Args:
            entity_id: Entity ID
            
        Returns:
            List of contacts
        """
        result = self._make_request(f"entity_contacts/{entity_id}/")
        return result if result else []
    
    def get_device_sessions(self, device_history: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process device history into organized sessions.
        
        Args:
            device_history: Raw device history from TOS
            
        Returns:
            List of device sessions with organized data
        """
        device_sessions = []
        devices_used = ["gnss_receiver", "antenna", "radome", "monument"]
        
        for connection in device_history.get("children_connections", []):
            # Skip zero-duration sessions
            if connection["time_from"] == connection["time_to"]:
                self.logger.debug(
                    f"Session start is the same as session end: {connection['time_from']}, end: {connection['time_to']}"
                )
                continue
            
            session = {
                "time_from": datetime.fromisoformat(connection["time_from"].replace('Z', '+00:00')) if connection["time_from"] else None,
                "time_to": datetime.fromisoformat(connection["time_to"].replace('Z', '+00:00')) if connection["time_to"] else None
            }
            
            # Add device information
            for device_type in devices_used:
                if device_type in connection:
                    device_info = connection[device_type]
                    if isinstance(device_info, dict):
                        session[device_type] = device_info
            
            device_sessions.append(session)
        
        return device_sessions


# Convenience functions for backward compatibility
def search_station(station_identifier: str, 
                  code: str = "marker",
                  url_rest: str = DEFAULT_TOS_URL,
                  domains: Optional[str] = None,
                  loglevel: int = logging.WARNING) -> List[Dict[str, Any]]:
    """
    Search for stations using TOS API.
    
    Args:
        station_identifier: Station identifier
        code: Search code type
        url_rest: TOS API base URL
        domains: Domain filter
        loglevel: Logging level
        
    Returns:
        List of matching stations
    """
    client = TOSClient(url_rest, loglevel=loglevel)
    return client.search_stations(station_identifier, code, domains)


def get_station_metadata(station_identifier: str,
                        url_rest: str = DEFAULT_TOS_URL,
                        loglevel: int = logging.WARNING) -> tuple[Optional[Dict], Optional[Dict]]:
    """
    Get station metadata from TOS API.
    
    Args:
        station_identifier: Station identifier
        url_rest: TOS API base URL  
        loglevel: Logging level
        
    Returns:
        Tuple of (station_data, device_history)
    """
    client = TOSClient(url_rest, loglevel=loglevel)
    return client.get_station_metadata(station_identifier)


def get_contacts(entity_id: int,
                url_rest: str = DEFAULT_TOS_URL,
                loglevel: int = logging.WARNING) -> List[Dict[str, Any]]:
    """
    Get contacts for an entity.
    
    Args:
        entity_id: Entity ID
        url_rest: TOS API base URL
        loglevel: Logging level
        
    Returns:
        List of contacts
    """
    client = TOSClient(url_rest, loglevel=loglevel)
    return client.get_contacts(entity_id)