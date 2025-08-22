# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-08-22

### Added

- **Major Project Restructure**: Converted to proper Python package structure
  - Created `pyproject.toml` with hatchling build system
  - Implemented `src/tostools/` package layout following modern Python standards
  - Added console scripts: `tosGPS`, `tos`, `json2ascii`, `metadata2rmq`
  - Created `tests/` directory for test files
  - Added comprehensive `.gitignore` for Python projects

### Changed

- **Identified Project Focus**: Clarified that `tosGPS` is the main GPS QC application
  - `tosGPS.py`: Main GPS metadata quality control tool (by Benedikt)
  - `tos.py`: Legacy TOS API client (by Tryggvi Hjörvar, kept for reference)
  - Proper attribution and documentation of code origins

### Fixed

- **File Organization**: Moved data/log files to `tmp/` directory (git-ignored)
  - RINEX data files (_.D,_.gz)
  - Log files (\*.log)
  - JSON configuration files
  - Station lists and antenna data
  - All data products now properly excluded from version control

### Dependencies

- Added `argparse-logging>=2020.11.26` for tosGPS functionality
- Specified all dependencies in pyproject.toml:
  - `requests>=2.31.0` (TOS API calls)
  - `pandas>=2.0.3` (data processing)
  - `tabulate>=0.9.0` (table formatting)
  - `gtimes>=0.3.3` (GPS time functions)
  - `python-dateutil>=2.9.0` (date utilities)

### Environment

- Confirmed mamba/conda environment: `tostools`
- Installation: `pip install -e .` (development mode)
- Dev dependencies: `pip install -e ".[dev]"` (pytest, black, ruff)

### Documentation

- Created comprehensive `CLAUDE.md` for future Claude Code sessions
- Updated `README.md` understanding (Icelandic content preserved)
- Documented package structure and console scripts
- Clear distinction between GPS tools (primary) vs TOS tools (legacy)

### Infrastructure

- **Git Setup**: Added dual remote configuration
  - `origin`: `git@git.vedur.is:bgo/tostools.git` (institutional, preserved)
  - `github`: `git@github.com:bennigo/tostools.git` (personal, active)
- **GitHub CLI**: Installed `gh` via conda-forge for repository management
- **Repository Created**: <https://github.com/bennigo/tostools> (public)
- **First Release**: Commit `bfe132e` pushed successfully to GitHub

## Git Repository Info

- **Active Remote**: `github` → <https://github.com/bennigo/tostools>
- **Institutional**: `origin` → git.vedur.is (preserved, untouched)
- **Branches**: master (currently tracking github/master)
- **Status**: All restructuring work committed and pushed

## [Unreleased]

### In Progress - Modular Architecture Refactoring (2025-08-22)

**MAJOR REFACTORING**: Converting monolithic modules into clean, modular architecture

#### ✅ Completed Analysis
- **Audited all core modules**: `gps_metadata_functions.py` (14 funcs), `gps_metadata_qc.py` (12 funcs), `gps_rinex.py` (11 funcs), `owner.py`
- **Categorized functions**: API, core business logic, presentation, file I/O, utilities
- **Identified separation concerns**: Mixed responsibilities in current modules

#### ✅ New Modular Structure Created
```
src/tostools/
├── cli/          # Command-line interfaces (pure UI logic)
├── api/          # TOS API client modules  
├── core/         # Core business logic & data models
├── rinex/        # RINEX processing (candidate for subcommand)
├── io/           # File I/O & formatting utilities
├── utils/        # Shared utilities (logging, etc.)
└── legacy/       # Original modules (transition period)
```

#### ✅ Infrastructure Modules Built
- **`utils/logging.py`**: Centralized logging with type hints & better configuration
- **`io/file_utils.py`**: File I/O for gzip/Z-compressed/text files with proper error handling
- **`io/formatters.py`**: Output formatting (tables, JSON) separated from business logic
- **`api/tos_client.py`**: Complete TOS API client with class-based design, error handling, type hints

#### 🎯 Key Improvements
- **Type hints throughout**: Better IDE support, code clarity, maintainability
- **Proper error handling**: Graceful failures with meaningful logging
- **Separation of concerns**: Business logic ↔ presentation ↔ I/O ↔ API
- **Class-based design**: More maintainable than scattered functions
- **Backward compatibility**: Convenience functions maintain existing interfaces

#### ✅ MAJOR MILESTONE COMPLETED (2025-08-22)

**🎉 FULLY FUNCTIONAL GPS TOOLKIT + MODULAR INFRASTRUCTURE READY**

- ✅ **`core/station.py` created**: Complete Station class with properties, session management, device queries
- ✅ **Fixed formatting bug**: tosGPS now works perfectly in both raw and regular formats  
- ✅ **Real-world testing**: Successfully shows GPS equipment history from 2000-2023
  - Equipment evolution: TRIMBLE 4000SSI → NETR9 → SEPT POLARX5
  - Antenna changes: TRM29659.00 → SEPCHOKE_B3E6
  - Radome changes: SCIS → SPKE
- ✅ **API integration**: Perfect connection to vi-api.vedur.is TOS system
- ✅ **Data quality**: Complete device history with timestamps, serial numbers, configurations

#### 🚀 **FINAL MIGRATION COMPLETED** (2025-08-22)

**✅ COMPLETE MODULAR ARCHITECTURE TRANSFORMATION SUCCESSFUL!**

- ✅ **Legacy Module Updates**: All three main legacy modules updated to use modular components:
  - `gps_metadata_qc.py`: Updated with modular logging, file I/O, and API client integration  
  - `gps_metadata_functions.py`: Replaced local logger with centralized logging system
  - `gps_rinex.py`: Key functions updated to use modular RINEX components (reader, editor, validator)

- ✅ **New CLI Interface Created**: `cli/main.py` - Clean separation of UI logic from business logic:
  - Pure argument parsing and user interface handling
  - Support for all output formats: table, JSON, raw
  - Verbose/debug logging modes with proper level control
  - Identical functionality to legacy interface, verified by output comparison

- ✅ **Complete RINEX Module Suite**: Ready for `tosGPS rinex` subcommand:
  - `rinex/reader.py`: File reading, header extraction, format detection
  - `rinex/validator.py`: RINEX vs TOS comparison, time range validation, QC reports  
  - `rinex/editor.py`: Header correction, IGS standards compliance, batch file updates

- ✅ **Comprehensive Testing**: Both legacy `tosGPS.py` and new `cli/main.py` produce identical output
  - Same 36-line output for test station VMEY
  - All GPS equipment history correctly displayed (2000-2023 data)
  - JSON, table, and raw formats all working perfectly
  
- ✅ **Full Backward Compatibility**: All existing functionality preserved during migration

### Previous Completed Items

- ✅ Test package installation: `pip install -e .`
- ✅ Validate console scripts work correctly (tosGPS + json2ascii working)
- ✅ Run tests to ensure functionality preserved (basic tests passing)
- ✅ CI/CD setup for automated testing (GitHub Actions workflow created)

## Notes for Future Sessions

- **Primary Application**: `tosGPS <stations>` - GPS metadata QC tool
- **Legacy TOS**: `tos <station>` - TOS API queries (Tryggvi's code)
- **Test Location**: `tests/test_*.py` files
- **Data Location**: `tmp/` directory (all data products, git-ignored)
- **Binary Tools**: `bin/` directory (RINEX processing tools)

