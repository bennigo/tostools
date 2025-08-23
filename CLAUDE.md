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

#### Clean Output (Default - Perfect for Automation)
- Station metadata: `tosGPS PrintTOS RHOF --format table > data.csv`
- Site log generation: `tosGPS sitelog RHOF | process_data.py`
- RINEX validation: `tosGPS rinex RHOF data/*.rnx`

#### Manual QC with Status Info
- With progress info: `tosGPS --log-level INFO PrintTOS RHOF --format table`
- Full debug output: `tosGPS --debug-all sitelog RHOF --output station.log`
- File logging: `tosGPS --log-dir logs PrintTOS RHOF`

#### Legacy Examples  
- Basic QC: `tosGPS REYK HOFN`
- With server options: `tosGPS REYK --server vi-api.vedur.is --port 443`
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

**⚠️ CRITICAL: RINEX Format Requirements**
- RINEX files use **strict FORTRAN77 column formatting**
- **Spaces vs tabs matter** - must use exact spacing, not tabs
- **Column alignment is critical** - each field has specific character positions
- **Extra spaces can break parsing** - FORTRAN77 readers are very strict
- When editing RINEX headers, preserve exact column positions and spacing

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

## CI/CD Pipeline

The project uses GitHub Actions for continuous integration and deployment. The workflow is defined in `.github/workflows/ci.yml`.

### Workflow Triggers
- **Push to master**: Runs full CI pipeline including publishing checks
- **Pull requests**: Runs testing and validation only

### CI Pipeline Steps

#### 1. **Testing Matrix**
- Tests across Python versions: 3.8, 3.9, 3.10, 3.11, 3.12, 3.13
- Ensures compatibility across supported Python versions

#### 2. **Code Quality Checks**
- **Linting**: `ruff check src/` - Fast Python linter for code quality
- **Formatting**: `black --check src/` - Ensures consistent code style
- **Dependencies**: All project and dev dependencies are installed via `pip install -e ".[dev]"`

#### 3. **Functional Testing**
- **Unit Tests**: `pytest tests/ -v` - Runs test suite with verbose output
- **Console Scripts**: Tests that main entry points work correctly
  - `tosGPS --help` - Main GPS QC application
  - `json2ascii --help` - JSON to ASCII converter

#### 4. **Package Building** (master branch only)
- **Build**: Creates source and wheel distributions using `python -m build`
- **Validation**: `twine check dist/*` verifies package integrity
- Only runs on successful tests and on master branch pushes

### Development Workflow Integration

#### Before Committing
```bash
# Run the same checks locally
ruff check src/
black --check src/
pytest tests/ -v
```

#### For New Features
1. Create feature branch from master
2. Develop and test locally
3. Push branch - triggers CI testing
4. Create PR - CI runs validation
5. Merge to master - triggers full pipeline including build validation

#### CI Failure Troubleshooting
- **Linting failures**: Run `ruff check src/` locally and fix issues
- **Format failures**: Run `black src/` to auto-format code
- **Test failures**: Run `pytest tests/ -v` locally to debug
- **Console script failures**: Ensure imports are correct and dependencies installed

### Key Benefits
- **Quality Assurance**: Prevents broken code from reaching master
- **Cross-Version Compatibility**: Tests against multiple Python versions
- **Automated Validation**: Ensures package builds correctly for distribution
- **Fast Feedback**: Immediate notification of issues via GitHub interface

### Monitoring CI Status
- Check the "Actions" tab on GitHub repository
- Green checkmark = All tests passed
- Red X = CI failure requiring attention
- Yellow dot = CI currently running

## File Structure

### New Modular Architecture (In Progress - 2025-08-22)

**MAJOR REFACTORING**: Converting to clean, modular architecture

```
src/tostools/
├── cli/                        # Command-line interfaces (pure UI logic)
│   ├── main.py                 # Main tosGPS CLI (refactored tosGPS.py)
│   └── rinex_cli.py            # tosGPS rinex subcommand
├── api/                        # TOS API client modules
│   ├── tos_client.py           # Main TOS API client (class-based)
│   └── contacts.py             # Contact/owner management  
├── core/                       # Core business logic & data models
│   ├── station.py              # Station data models
│   ├── device.py               # Device history & session management
│   └── metadata.py             # Metadata processing
├── rinex/                      # RINEX processing modules
│   ├── reader.py               # RINEX file reading/parsing
│   ├── validator.py            # RINEX vs TOS QC validation
│   └── editor.py               # RINEX header editing/fixing
├── io/                         # Input/Output utilities
│   ├── file_utils.py           # File I/O (gzip, Z, text) [CREATED]
│   └── formatters.py           # Output formatting [CREATED]
├── utils/                      # Shared utilities
│   └── logging.py              # Logging configuration [CREATED]
└── legacy/                     # Original modules (transition period)
    ├── gps_metadata_functions.py
    ├── gps_metadata_qc.py
    ├── gps_rinex.py
    └── owner.py
```

**🎉 MAJOR MILESTONES**: 

**2025-08-22**: Modular Architecture Foundation
- **Fully Functional**: tosGPS works perfectly with real GPS data (2000-2023 equipment history)
- **Modular Infrastructure**: Complete new architecture ready for migration
- **Key Improvements**: Type hints, proper error handling, separation of concerns, class-based design, backward compatibility
- **Ready for Migration**: All legacy functions categorized, new modules built, working baseline established

**2025-08-23**: Production-Ready Logging System & Manual QC Optimization
- **🚀 CLEAN OUTPUT BY DEFAULT**: All commands (PrintTOS, rinex, sitelog) produce completely clean output
- **Enterprise Logging**: Comprehensive file logging with level separation and structured JSON output  
- **Manual QC Optimized**: Silent operation by default, verbose output available on demand
- **Unix Standards Compliant**: stdout for data, stderr for status messages, proper exit codes
- **✅ FINAL LOGGING**: Eliminated ALL legacy logger bypasses - no more verbose debug pollution
- **🌐 ENGLISH CONTACT ROLES**: PrintTOS now displays "Owner"/"Operator" instead of Icelandic text
- **📊 COMPREHENSIVE TESTING**: All three main commands fully tested with real GPS station data
- **🔧 RINEX COMPLIANCE**: FORTRAN77 formatting requirements documented and enforced

### Legacy Structure
- **tests/**: Test files (moved from src)
- **bin/**: Binary tools for RINEX processing (CRX2RNX, anubis, etc.)
- **import_scripts/**: Database import utilities for meteorological data
- **tmp/**: Data files, logs, and configuration files (git-ignored)
  - Station data: `*.list`, `*.info` files
  - RINEX data: `*.D`, `*.gz` files  
  - Log files: `*.log` files from station processing
  - JSON configs: `*.json` files with station information

## Manual QC Workflow Optimization (2025-08-23)

### Clean Output by Default
All tosGPS commands now produce clean output perfect for automation and scripting:

```bash
# Clean data extraction - no logging noise
tosGPS PrintTOS RHOF --format table > station_data.csv

# Pipeline-friendly site log generation  
tosGPS sitelog RHOF | grep "Antenna" | process_metadata.py

# Silent RINEX validation for batch processing
tosGPS rinex RHOF data/*.rnx 2>/dev/null
```

### Verbose Output When Needed
Full logging control available for debugging and manual inspection:

```bash
# Progress information for manual QC
tosGPS --log-level INFO PrintTOS RHOF --format table

# Complete debug output for troubleshooting
tosGPS --debug-all --log-dir logs sitelog RHOF

# File logging for comprehensive analysis
tosGPS --log-dir logs --log-format json PrintTOS RHOF
```

### Output Stream Architecture
- **stdout**: Program data (tables, site logs, validation results) - perfect for piping
- **stderr**: Status messages, progress info, errors - can be silenced with `2>/dev/null`
- **Files**: Comprehensive logging with level separation when `--log-dir` used