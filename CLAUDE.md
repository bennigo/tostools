# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is tostools, a Python3 command-line toolkit primarily for GPS/GNSS station metadata quality control and processing. The project combines:

1. **Primary GPS Tools** (by Benedikt): GPS metadata QC, RINEX processing, station management
2. **Legacy TOS Integration** (by Tryggvi): Tools for querying TOS API for Icelandic weather/seismic stations

**Main Application**: `tosGPS` - GPS metadata quality control tool that queries TOS API and validates against RINEX files.

## Environment Setup

This project uses a dedicated mamba/conda environment named `tostools`. 

### Activating the Environment
```bash
mamba activate tostools
# or
conda activate tostools
```

### Installation
Install in development mode after activating the environment:
```bash
mamba activate tostools
pip install -e .
```

### Core Usage
- **Primary GPS QC**: `tosGPS <station1> <station2> ...` (main application)
- **Legacy TOS queries**: `tos <station_identifier>` (from Tryggvi's TOSTools)
- Convert JSON to ASCII: `json2ascii input.json output.txt` 
- Process metadata for RMQ: `metadata2rmq`
- Run tests: `pytest tests/`

### tosGPS Examples
- Basic QC: `tosGPS REYK HOFN`
- With server options: `tosGPS REYK --server vi-api.vedur.is --port 443`
- Print as table: `tosGPS REYK PrintTOS --format table`
- Print raw format: `tosGPS REYK PrintTOS --raw`

### Development Dependencies
Install development dependencies:
```bash
pip install -e ".[dev]"
```

### Dependencies
The project dependencies are managed through pyproject.toml and include:
- `requests` (for TOS API calls)
- `pandas` (for data processing) 
- `tabulate` (for table formatting)
- `gtimes` (GPS time functions)
- `python-dateutil` (date utilities)

### Legacy TOS Query Examples (from Tryggvi's TOSTools)
- Search stations: `tos vadla`, `tos ada`, `tos V89`
- Search by serial number: `tos -s 182820302`
- Search by Galvos number: `tos -G 10001`
- Output formats: `tos vadla -o json|table|pretty`
- Domain filtering: `tos ada -D geophysical`

## Architecture

### Package Structure
```
src/tostools/
├── tosGPS.py                   # Main GPS QC application (console script: tosGPS)
├── gps_metadata_functions.py  # GPS station metadata processing (Benedikt)
├── gps_metadata_qc.py         # GPS quality control functions (Benedikt)
├── gps_rinex.py               # RINEX file processing utilities (Benedikt)
├── metadata_functions.py      # Generic metadata utilities (Benedikt)  
├── metadata2rmq.py            # Metadata to RMQ processor (Benedikt)
├── json2ascii.py              # JSON to ASCII converter
├── owner.py                   # Ownership/contact utilities
├── rmqdict.py                 # RMQ dictionary utilities
├── tos.py                     # TOS API client - legacy (Tryggvi)
└── xmltools.py                # XML processing for seismic data (Tryggvi)
```

### Key Data Sources
- TOS API: `https://vi-api.vedur.is:11223/tos/v1` (Icelandic weather/seismic stations)
- Local station databases: `stations.list`, `station.info.sopac.apr05`
- Binary tools: `bin/` contains RINEX conversion utilities (CRX2RNX, RNX2CRX, anubis)

### Station Types Handled
- Meteorological stations
- Geophysical/seismic stations (SIL network)
- Hydrological stations  
- Remote sensing platforms
- GPS/GNSS stations

### XML Generation
The project can generate:
- SC3ML (SeisComP3) format for seismic networks
- FDSN StationXML format
- Station metadata exports

## Development Notes

- Language: The README and station data are in Icelandic, but code is in English
- Python version: Requires Python 3.6+
- No formal requirements.txt - dependencies noted in README
- Test files: `test_tos.py`, `test_tostool.py` for testing functionality
- Logging: Uses custom logger setup in `metadata_functions.py`

## File Structure

- **src/tostools/**: Main package source code
- **tests/**: Test files (moved from src)
- **bin/**: Binary tools for RINEX processing (CRX2RNX, anubis, etc.)
- **import_scripts/**: Database import utilities for meteorological data
- **tmp/**: Data files, logs, and configuration files (git-ignored)
  - Station data: `*.list`, `*.info` files
  - RINEX data: `*.D`, `*.gz` files  
  - Log files: `*.log` files from station processing
  - JSON configs: `*.json` files with station information