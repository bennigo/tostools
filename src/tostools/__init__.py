"""
tostools: Python toolkit for GPS/GNSS station management and TOS API integration

This package provides tools for:
- GPS metadata quality control and validation (main: tosGPS)
- Processing GPS/GNSS station metadata and RINEX files  
- Querying TOS (Technical Operations System) API for Icelandic weather/seismic stations
- XML generation for seismic networks (SC3ML, FDSN StationXML)

Main Components:
- tosGPS: GPS metadata QC tool (primary application)
- tos.py: TOS API client (legacy from TOSTools by Tryggvi Hjörvar)
- GPS processing modules: metadata functions, QC, RINEX processing
"""

__version__ = "0.1.0"
__author__ = "Benedikt Gunnar Ófeigsson, Tryggvi Hjörvar" 
__email__ = "bgo@vedur.is"

# Primary GPS functions
from .gps_metadata_functions import print_station_history
from .gps_metadata_qc import gps_metadata
from .gps_rinex import *

# Legacy TOS functions (from Tryggvi's TOSTools)
from .tos import searchStation, searchDevice

__all__ = [
    "print_station_history",
    "gps_metadata", 
    "searchStation",
    "searchDevice",
]