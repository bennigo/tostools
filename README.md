# tostools

**GPS Metadata Quality Control & TOS API Toolkit**

A Python3 command-line toolkit for GPS/GNSS station metadata quality control, RINEX processing, and TOS API integration. Combines GPS station validation tools with Icelandic weather/seismic station queries.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🚀 Quick Start

```bash
# Install in development mode
mamba activate tostools  # or conda activate tostools
pip install -e .

# GPS station metadata with rich formatting
tosGPS PrintTOS RHOF

# Generate GAMIT processing file
tosGPS PrintTOS RHOF REYK --format gamit > stations.info

# Validate RINEX files
tosGPS rinex RHOF data/RHOF*.rnx

# Generate IGS site log
tosGPS sitelog RHOF --output RHOF.log
```

## 📋 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [GPS Tools](#-gps-tools)
- [TOS API Tools](#-tos-api-tools)
- [Output Formats](#-output-formats)
- [Examples](#-examples)
- [Architecture](#-architecture)
- [Development](#-development)
- [License](#-license)

## ✨ Features

### 🛰️ GPS Metadata Quality Control
- **Rich Visual Display**: Color-coded equipment tables optimized for manual QC
- **GAMIT/GLOBK Integration**: Production-ready format for GPS processing workflows  
- **RINEX Validation**: Compare RINEX headers against TOS metadata
- **Site Log Generation**: IGS-compliant site logs with complete station history
- **Robust Data Validation**: Prevents processing crashes with smart error handling

### 🌐 TOS API Integration
- **Station Search**: Query Icelandic weather/seismic stations by name or ID
- **Equipment History**: Complete device and sensor change tracking
- **Multiple Domains**: Meteorological, geophysical, hydrological stations
- **Contact Management**: Owner and operator information in multiple languages

### 🎨 Professional Output
- **Rich Tables**: Color-coded equipment groups with proper alignment
- **Multiple Formats**: Table, JSON, GAMIT, rich visual displays
- **Clean Data Export**: Perfect for automation and data pipelines
- **Selective Display**: Show only the data sections you need

## 🔧 Installation

### Prerequisites
- Python 3.8+ (supports up to Python 3.13)
- Recommended: Mamba or Conda for environment management

### Environment Setup
```bash
# Create dedicated environment
mamba create -n tostools python=3.11
mamba activate tostools

# Install from repository
git clone https://github.com/bennigo/tostools.git
cd tostools
pip install -e .

# Or install development dependencies
pip install -e ".[dev]"
```

### Dependencies
The package automatically installs:
- `requests` - TOS API communication
- `pandas` - Data processing and analysis
- `tabulate` - Simple table formatting  
- `rich` - Enhanced terminal output with colors
- `gtimes` - GPS time functions
- `python-dateutil` - Date/time utilities
- `fortranformat` - RINEX FORTRAN77 parsing
- `pyproj` - Coordinate transformations
- `argparse-logging` - Enhanced CLI logging

## 🛰️ GPS Tools

### PrintTOS - Station Metadata Display

**Rich Visual Output** (Default - Perfect for Manual QC)
```bash
# Enhanced color-coded tables
tosGPS PrintTOS RHOF                    # Rich format (default)
tosGPS PrintTOS RHOF --format rich      # Explicit rich format

# Show only specific sections
tosGPS PrintTOS RHOF --show-history     # Device history only
tosGPS PrintTOS RHOF --show-static --show-contacts  # Static + contacts

# Detailed contact information  
tosGPS PrintTOS RHOF --contact          # English/Icelandic details
```

**Clean Data Export** (Perfect for Automation)
```bash
# Simple table format
tosGPS --log-level ERROR PrintTOS RHOF --format table > station_data.csv

# JSON for data processing
tosGPS PrintTOS RHOF --format json | jq .

# Multiple stations
tosGPS PrintTOS REYK HOFN RHOF --format table
```

**GAMIT/GLOBK Processing**
```bash
# Generate stations.info file for GPS processing
tosGPS PrintTOS RHOF REYK --format gamit > stations.info

# Includes robust data validation and error handling
# Skips invalid sessions while preserving valid ones
# Critical data issues visible at ERROR logging level
```

### RINEX Validation

```bash
# Basic validation (results to stdout)
tosGPS rinex RHOF data/RHOF*.rnx

# Validate with progress information
tosGPS --log-level INFO rinex RHOF data/RHOF0790.02D

# Apply corrections with backup
tosGPS rinex RHOF data/RHOF0790.02D --fix --backup

# Generate QC report
tosGPS rinex RHOF data/*.rnx --report qc_report.txt

# Silent validation for scripting
tosGPS --log-level ERROR rinex RHOF file.rnx 2>/dev/null
echo $?  # Check exit code: 0=success, 1=discrepancies
```

### Site Log Generation

```bash
# Output to stdout (pipe-friendly)
tosGPS sitelog RHOF
tosGPS sitelog RHOF | grep "Antenna"

# Save to file
tosGPS sitelog RHOF --output RHOF_site.log

# Process multiple stations
for station in REYK HOFN RHOF; do
    tosGPS sitelog $station --output logs/${station}.log
done
```

## 🌐 TOS API Tools

### Legacy TOS Queries (Icelandic Stations)

```bash
# Station search
tos vadla                    # Search by name
tos ada                      # Partial name search  
tos V89                      # Station ID search

# Equipment search
tos -s 182820302             # By serial number
tos -G 10001                 # By Galvos number

# Output formats
tos vadla -o json            # JSON output
tos vadla -o table           # Table format
tos vadla -o pretty          # Pretty format (default)

# Domain filtering
tos ada -D geophysical       # Geophysical stations only
```

### Utility Tools

```bash
# Convert JSON to ASCII
json2ascii input.json output.txt

# Process metadata for RMQ
metadata2rmq
```

## 📊 Output Formats

### Rich Format (Default)
- **Color-coded equipment groups**: Receiver (green), Antenna (red), Monument (yellow)
- **Professional layout**: Compact spacing optimized for terminal viewing
- **Complete data visibility**: No truncation, proper decimal alignment
- **Contact information**: Clean tables with English/Icelandic translations

### Table Format
- **Simple tabular output**: Perfect for CSV export and data analysis
- **Script-friendly**: Clean format for automated processing
- **Pipe-compatible**: Works seamlessly with Unix tools

### GAMIT Format
- **GPS Processing Ready**: Fixed-width columns with proper headers
- **Robust Validation**: Invalid sessions skipped, valid sessions preserved
- **Production Tested**: Compatible with GAMIT/GLOBK workflows
- **Error Reporting**: Clear logging of data quality issues

### JSON Format
- **Complete metadata**: All station information in structured format
- **API Integration**: Perfect for web services and data pipelines
- **Processing Scripts**: Easy parsing with jq and other JSON tools

## 🔄 Examples

### Manual Quality Control Workflow
```bash
# 1. Review station with rich visual display
tosGPS PrintTOS RHOF --format rich

# 2. Check specific equipment history
tosGPS PrintTOS RHOF --show-history

# 3. Verify contact information
tosGPS PrintTOS RHOF --contact

# 4. Validate against RINEX files
tosGPS rinex RHOF data/RHOF*.rnx --report validation.txt

# 5. Generate site log if needed
tosGPS sitelog RHOF --output RHOF.log
```

### GPS Processing Preparation
```bash
# Generate GAMIT stations file with validation
tosGPS PrintTOS RHOF REYK HOFN --format gamit > stations.info

# Check for any data quality issues
tosGPS --log-level ERROR PrintTOS RHOF REYK HOFN --format gamit

# Process with logging for quality control
tosGPS --log-dir logs PrintTOS RHOF REYK --format gamit > stations.info
```

### Automated Data Pipeline
```bash
# Clean data extraction for automation
tosGPS --log-level ERROR PrintTOS RHOF --format table > station_data.csv

# JSON processing pipeline
tosGPS PrintTOS RHOF --format json | jq '.device_history[] | .time_from' 

# Batch validation
for file in data/*.rnx; do
    tosGPS --log-level ERROR rinex RHOF "$file" || echo "Issue in $file"
done
```

### Legacy TOS Integration
```bash
# Search Icelandic weather stations
tos vadla -o json > vadla_station.json

# Find equipment by serial number
tos -s A086 -o table

# Geophysical network query
tos -D geophysical reyk
```

## 🏗️ Architecture

### Modular Design (v0.2.3+)
```
src/tostools/
├── cli/                    # Command-line interfaces
│   ├── main.py            # Modern modular CLI
│   └── rinex_cli.py       # RINEX processing commands
├── io/                    # Input/Output formatting
│   ├── rich_formatters.py # Rich table display
│   └── formatters.py      # JSON/table formatters
├── utils/                 # Utilities
│   └── logging.py         # Production logging system
├── tosGPS.py              # Main GPS QC application (legacy compatible)
└── legacy/                # Original modules (transitioning)
    ├── gps_metadata_*.py # GPS processing functions
    └── tos.py             # TOS API client
```

### Key Features
- **Clean Output by Default**: All commands produce automation-friendly output
- **Rich Visual Mode**: Enhanced tables for manual quality control
- **Robust Error Handling**: Graceful handling of real-world data issues
- **Production Logging**: Comprehensive file logging with level separation
- **Backward Compatibility**: Legacy interfaces maintained during transition

## 👨‍💻 Development

### Running Tests
```bash
# Install development dependencies
pip install -e ".[dev]"

# Run test suite
pytest tests/ -v

# Test console scripts
tosGPS --help
json2ascii --help
```

### Code Quality
```bash
# Linting
ruff check src/

# Formatting  
black src/

# Full CI pipeline locally
ruff check src/ && black --check src/ && pytest tests/ -v
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure CI pipeline passes
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Benedikt G. Ófeigsson** - GPS metadata QC and RINEX processing tools
- **Tryggvi Hjörvar** - Original TOS API integration and Icelandic station tools
- **Icelandic Meteorological Office (IMO)** - TOS API and station data
- **GAMIT/GLOBK** - GPS processing software compatibility

## 📞 Contact

- **Email**: bgo@vedur.is (Benedikt) or hildur@vedur.is (Hildur)
- **Issues**: [GitHub Issues](https://github.com/bennigo/tostools/issues)
- **TOS API**: [https://tos.vedur.is](https://tos.vedur.is)

---

**Version**: 0.2.3 | **Python**: 3.8+ | **Status**: Production Ready