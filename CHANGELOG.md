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
  - RINEX data files (*.D, *.gz)
  - Log files (*.log)  
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
- **Repository Created**: https://github.com/bennigo/tostools (public)
- **First Release**: Commit `bfe132e` pushed successfully to GitHub

## Git Repository Info
- **Active Remote**: `github` → https://github.com/bennigo/tostools
- **Institutional**: `origin` → git.vedur.is (preserved, untouched)
- **Branches**: master (currently tracking github/master)
- **Status**: All restructuring work committed and pushed

## [Unreleased]
### Next Steps
- Test package installation: `pip install -e .`
- Validate console scripts work correctly  
- Run tests to ensure functionality preserved
- Consider CI/CD setup for automated testing

## Notes for Future Sessions
- **Primary Application**: `tosGPS <stations>` - GPS metadata QC tool
- **Legacy TOS**: `tos <station>` - TOS API queries (Tryggvi's code)
- **Test Location**: `tests/test_*.py` files
- **Data Location**: `tmp/` directory (all data products, git-ignored)
- **Binary Tools**: `bin/` directory (RINEX processing tools)