#!python

import argparse
import logging
import sys
from pathlib import Path

from argparse_logging import add_log_level_argument

from . import gps_metadata_functions as gpsf
from . import gps_metadata_qc as gpsqc

# Import new modular components
from .api.tos_client import TOSClient
from .core.site_log import generate_igs_site_log
from .rinex.editor import update_rinex_files
from .rinex.reader import extract_header_info, read_rinex_header
from .rinex.validator import compare_rinex_to_tos

# Import new logging system
from .utils.logging import (
    setup_development_logging, 
    setup_production_logging, 
    setup_console_logging,
    get_logger,
    LoggingConfig,
    configure_logging
)


def _configure_logging(args):
    """Configure the logging system based on command line arguments."""
    # Determine console log level
    console_level = args.log_level.value if hasattr(args.log_level, 'value') else args.log_level
    
    # For manual QC workflow: default to minimal console logging
    # unless explicitly requested by user
    if hasattr(args, 'subcommand') and args.subcommand in ['PrintTOS', 'rinex', 'sitelog']:
        # Manual QC commands: Keep console clean by default
        if console_level == logging.INFO and not args.debug_all:
            console_level = logging.ERROR  # Only show errors for clean output (warnings/errors can be enabled explicitly)
    
    # Smart console level: debug-all enables DEBUG for files but keeps console cleaner
    if args.debug_all and args.log_dir:
        # When file logging is available, keep console at INFO level for readability
        # but enable DEBUG for files
        file_level = logging.DEBUG
        if console_level == logging.WARNING:  # From manual QC logic above
            console_level = logging.INFO  # Show some progress info when debug-all is requested
    elif args.debug_all:
        # No file logging, so show DEBUG on console
        console_level = logging.DEBUG
        file_level = logging.DEBUG
    else:
        file_level = logging.DEBUG if not args.production_logging else logging.INFO
    
    if args.log_dir:
        # File logging enabled
        if args.production_logging:
            configure_logging(LoggingConfig(
                console_level=console_level,
                file_level=logging.INFO,
                log_dir=args.log_dir,
                console_format=args.log_format,
                file_format="json",
                structured_file=True,
                separate_levels=True,
            ), force_reconfigure=True)
        else:
            # Development logging - keep console clean but files comprehensive
            configure_logging(LoggingConfig(
                console_level=console_level,  # Respect user's level choice
                file_level=file_level,        # Use DEBUG for files when --debug-all
                log_dir=args.log_dir,
                console_format=args.log_format,
                file_format="human",
                structured_file=True,
                separate_levels=True,
            ), force_reconfigure=True)
    else:
        # Console only logging
        setup_console_logging(console_level)


def main():
    """
    quering metadata from tos and comparing to relevant rinex files
    """

    url_rest_tos = "vi-api.vedur.is/tos/v1"
    stationInfo_list = []

    # print(module_logger.getEffectiveLevel())

    parser = argparse.ArgumentParser(
        description="GPS metadata quality control and RINEX processing toolkit",
        epilog="""
QUICK START:
  # View station metadata  
  tosGPS PrintTOS RHOF --format table
  
  # Validate RINEX files
  tosGPS rinex RHOF data/RHOF*.rnx
  
  # Generate site log
  tosGPS sitelog RHOF --output RHOF.log
  
LOGGING CONTROL:
  --log-level ERROR    # Clean output (recommended for scripting)
  --log-dir logs/      # Enable comprehensive file logging  
  --debug-all          # Detailed debug info (to files when --log-dir used)

OUTPUT STREAMS:
  stdout: Program data (tables, validation results, site logs)
  stderr: Status messages, progress, errors (use 2>/dev/null to hide)

For detailed examples, use: tosGPS COMMAND --help

Contact: Benni (bgo@vedur.is) or Hildur (hildur@vedur.is)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    add_log_level_argument(parser)

    # Logging options
    logging_options = parser.add_argument_group(title="Logging options")
    logging_options.add_argument(
        "--log-dir", type=str, help="Directory for log files (enables file logging)"
    )
    logging_options.add_argument(
        "--log-format", choices=["human", "json"], default="human",
        help="Log format (human-readable or structured JSON)"
    )
    logging_options.add_argument(
        "--production-logging", action="store_true",
        help="Use production logging configuration (less verbose)"
    )
    logging_options.add_argument(
        "--debug-all", action="store_true",
        help="Enable debug logging for all modules"
    )

    # server options
    server_options = parser.add_argument_group(title="Server options")
    server_options.add_argument(
        "--protocol", type=str, default="https", help="Transfer protocol"
    )
    server_options.add_argument(
        "-s", "--server", type=str, default="vi-api.vedur.is", help="Host:"
    )
    server_options.add_argument("-p", "--port", type=int, default=443, help="Port:")
    server_options.add_argument(
        "-r", "--rest", type=str, default="/tos/v1", help="Top levels REST path"
    )
    server_options.add_argument(
        "-t", "--timeout", type=int, default=4, help="Connection timeout:"
    )

    # making subcommands
    subparsers = parser.add_subparsers(
        title="Subcommands", description="valid subcommands", dest="subcommand", required=True
    )

    # For TOS print options
    print_options = subparsers.add_parser(
        "PrintTOS", 
        help="Display GPS station metadata from TOS in various formats",
        epilog="""
Examples:
  # Rich visual output (default - best for manual QC)
  tosGPS PrintTOS RHOF --format rich
  
  # Clean table output (perfect for analysis)  
  tosGPS --log-level ERROR PrintTOS RHOF --format table > station_data.csv
  
  # Show only device history
  tosGPS PrintTOS RHOF --show-history
  
  # Show only static data and contacts
  tosGPS PrintTOS RHOF --show-static --show-contacts
  
  # Detailed contact information
  tosGPS PrintTOS RHOF --contact
  
  # Multiple stations with status info
  tosGPS PrintTOS REYK HOFN RHOF --format table
  
  # GAMIT processing format
  tosGPS PrintTOS RHOF --format gamit > gamit_stations.dat
  
  # JSON output for scripting
  tosGPS PrintTOS RHOF --format json | jq .
  
  # Silent operation (errors only)
  tosGPS --log-level ERROR PrintTOS RHOF 2>/dev/null
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    print_options.add_argument("stations", nargs="+", help="List of stations")
    print_options.add_argument(
        "-f",
        "--format",
        choices=["table", "rich", "json", "gamit"],
        default="rich",
        help="Output format: rich (enhanced tables), table (simple), json, gamit (processing)",
    )
    print_options.add_argument("--raw", action="store_true", help="Include detailed raw metadata")
    
    # Display control options
    display_group = print_options.add_argument_group("Display options")
    display_group.add_argument(
        "--show-static", action="store_true",
        help="Show only static station data"
    )
    display_group.add_argument(
        "--show-history", action="store_true",
        help="Show only device history"
    )
    display_group.add_argument(
        "--show-contacts", action="store_true",
        help="Show only contact summary" 
    )
    display_group.add_argument(
        "--contact", action="store_true",
        help="Show detailed contact information in English and Icelandic"
    )

    # RINEX validation subcommand
    rinex_parser = subparsers.add_parser(
        "rinex", 
        help="Validate RINEX files against TOS metadata and apply corrections",
        epilog="""
Examples:
  # Basic validation (results to stdout)
  tosGPS --log-level ERROR rinex RHOF data/RHOF*.rnx
  
  # Validate with detailed progress
  tosGPS rinex RHOF data/RHOF0790.02D
  
  # Apply corrections with backup
  tosGPS rinex RHOF data/RHOF0790.02D --fix --backup
  
  # Generate QC report
  tosGPS rinex RHOF data/*.rnx --report qc_report.txt
  
  # Silent validation for scripting
  tosGPS --log-level ERROR rinex RHOF file.rnx 2>/dev/null
  echo $?  # Check exit code: 0=success, 1=discrepancies
  
  # Batch processing
  for file in data/*.rnx; do
      tosGPS --log-level ERROR rinex RHOF "$file" || echo "Issue in $file"
  done
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    rinex_parser.add_argument("stations", nargs="+", help="GPS stations to validate against")
    rinex_parser.add_argument(
        "rinex_files", nargs="+", help="RINEX files to validate"
    )
    rinex_parser.add_argument(
        "--fix", action="store_true", help="Apply corrections to RINEX headers"
    )
    rinex_parser.add_argument(
        "--backup", action="store_true", help="Create backup files before fixing"
    )
    rinex_parser.add_argument(
        "--report", type=str, help="Generate detailed QC report to file"
    )

    # Site log generation subcommand  
    sitelog_parser = subparsers.add_parser(
        "sitelog", 
        help="Generate IGS site log",
        epilog="""
Examples:
  # Output to stdout (pipe-friendly)
  tosGPS sitelog RHOF                          
  tosGPS sitelog RHOF | grep "Antenna"
  
  # Save to specific file
  tosGPS sitelog RHOF --output RHOF_site.log
  tosGPS sitelog RHOF -o logs/stations/RHOF.txt
  
  # Process multiple stations 
  for station in REYK HOFN RHOF; do
      tosGPS sitelog $station | process_sitelog.py $station
  done
  
  # Send to remote system
  tosGPS sitelog RHOF | ssh server "cat > /data/RHOF.log"
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sitelog_parser.add_argument("stations", nargs="+", help="List of stations")
    sitelog_parser.add_argument(
        "--output", "-o", type=str, 
        help="Output file (default: stdout for piping)"
    )

    args = parser.parse_args()
    stations = getattr(args, 'stations', [])
    
    # Configure logging system
    _configure_logging(args)
    
    # Get main logger
    logger = get_logger(__name__)
    
    # Constructing the URL:
    url = "{}://{}:{}{}".format(args.protocol, args.server, args.port, args.rest)
    log_level = args.log_level
    
    logger.info("tosGPS started", extra={
        "subcommand": args.subcommand,
        "stations": stations,
        "server_url": url,
        "log_level": log_level.name if hasattr(log_level, 'name') else str(log_level)
    })

    # Handle different subcommands
    if args.subcommand == "rinex":
        _handle_rinex_subcommand(args, stations, url, log_level)
    elif args.subcommand == "sitelog":
        _handle_sitelog_subcommand(args, stations, url, log_level)
    elif args.subcommand == "PrintTOS":
        _handle_print_subcommand(args, stations, url, log_level)
    else:
        # Default behavior - print station information
        _handle_print_subcommand(args, stations, url, log_level)


def _handle_print_subcommand(args, stations, url, log_level):
    """Handle PrintTOS subcommand and default behavior."""
    stationInfo_list = []

    # Defining default behaviour
    pformat, raw = (
        (args.format, args.raw) if args.subcommand == "PrintTOS" else ("rich", False)
    )
    
    # Process show options - if any --show-* flag is used, show only those sections
    # If no --show-* flags are used, show everything (default behavior)
    show_static_flag = getattr(args, 'show_static', False)
    show_history_flag = getattr(args, 'show_history', False) 
    show_contacts_flag = getattr(args, 'show_contacts', False)
    detailed_contacts = getattr(args, 'contact', False)
    
    # If any --show-* flag is specified, only show those sections
    any_show_flag = show_static_flag or show_history_flag or show_contacts_flag
    
    if any_show_flag:
        # Selective display mode - show only requested sections
        show_options = {
            "show_static": show_static_flag,
            "show_history": show_history_flag,
            "show_contacts": show_contacts_flag,
        }
    else:
        # Default mode - show everything unless --contact is used (which shows only contacts)
        if detailed_contacts:
            show_options = {
                "show_static": False,
                "show_history": False, 
                "show_contacts": False,  # Will be handled by detailed_contacts
            }
        else:
            show_options = {
                "show_static": True,
                "show_history": True,
                "show_contacts": True,
            }

    for sta in stations:
        station_info = gpsqc.gps_metadata(sta, url, loglevel=log_level.value)
        
        if not station_info:
            continue
            
        if pformat == "table":
            gpsf.print_station_history(
                station_info, raw_format=raw, loglevel=log_level.value
            )
        elif pformat == "rich":
            # Use new rich formatter with full flag support
            from .io.rich_formatters import print_stations_rich
            print_stations_rich(
                [station_info], 
                show_static=show_options["show_static"],
                show_contacts=show_options["show_contacts"],
                show_history=show_options["show_history"], 
                detailed_contacts=detailed_contacts
            )
        elif pformat == "json":
            # Use JSON formatter
            from .io.formatters import json_print
            print(json_print(station_info))
        elif pformat == "gamit":
            stationInfo_list += gpsf.print_station_history(station_info)

    # Handle gamit format output (accumulated at the end)
    if pformat == "gamit":
        stationInfo_list.sort()
        for infoline in stationInfo_list:
            print(infoline)


def _handle_rinex_subcommand(args, stations, url, log_level):
    """Handle RINEX validation and correction subcommand."""
    from pathlib import Path

    print(f"RINEX QC for stations: {', '.join(stations)}", file=sys.stderr)

    # Initialize TOS client
    tos_client = TOSClient(base_url=url)  # Use default, respect centralized logging

    all_comparisons = []

    for station in stations:
        print(f"\n=== Processing station {station} ===", file=sys.stderr)

        # Get station metadata using legacy system (more reliable for validation)
        try:
            station_data = gpsqc.gps_metadata(station, url, loglevel=log_level.value)
            if not station_data:
                print(f"Error: Could not retrieve metadata for station {station}", file=sys.stderr)
                continue

            # Extract device sessions for validation (use most recent)
            device_sessions = station_data.get('device_history', [])
            if not device_sessions:
                print(f"Warning: No device history found for station {station}", file=sys.stderr)
                continue

            # Use the most recent session for validation
            current_session = device_sessions[-1]

        except Exception as e:
            print(f"Error retrieving station data: {e}", file=sys.stderr)
            continue

        # Validate each RINEX file
        for rinex_file in args.rinex_files:
            rinex_path = Path(rinex_file)
            if not rinex_path.exists():
                print(f"Warning: RINEX file {rinex_file} not found", file=sys.stderr)
                continue

            print(f"\nValidating RINEX file: {rinex_file}", file=sys.stderr)

            # Read RINEX header
            header_data = read_rinex_header(rinex_path, log_level.value)
            if not header_data:
                print(f"Error reading RINEX header from {rinex_file}", file=sys.stderr)
                continue

            # Extract header information
            rinex_info = extract_header_info(header_data, log_level.value)

            # Compare with TOS metadata
            comparison = compare_rinex_to_tos(rinex_info, station_data, log_level.value)
            all_comparisons.append({
                'station': station,
                'file': rinex_file,
                'comparison': comparison
            })

            # Report discrepancies
            if comparison.get("discrepancies"):
                print(f"Found {len(comparison['discrepancies'])} discrepancies:", file=sys.stderr)
                for field, diff in comparison['discrepancies'].items():
                    print(f"  {field}: RINEX='{diff.get('rinex', '')}' vs TOS='{diff.get('tos', '')}'", file=sys.stderr)
            else:
                print("✓ No discrepancies found")

            # Apply fixes if requested
            if args.fix and comparison.get("corrections"):
                print(f"Applying {len(comparison['corrections'])} corrections...", file=sys.stderr)
                success = update_rinex_files(
                    [rinex_path],
                    [comparison['corrections']],
                    backup=args.backup,
                    loglevel=log_level.value
                )
                if success.get(str(rinex_path)):
                    print("✓ Corrections applied successfully", file=sys.stderr)
                else:
                    print("✗ Failed to apply corrections", file=sys.stderr)

    # Generate report if requested
    if args.report and all_comparisons:
        report_content = "GPS RINEX QC REPORT\n" + "="*50 + "\n\n"
        for item in all_comparisons:
            report_content += f"Station: {item['station']}\n"
            report_content += f"File: {item['file']}\n"
            comp = item['comparison']
            report_content += f"Discrepancies: {len(comp.get('discrepancies', {}))}\n"
            report_content += f"Corrections: {len(comp.get('corrections', {}))}\n\n"

        try:
            with open(args.report, 'w') as f:
                f.write(report_content)
            print(f"\n✓ QC report saved to {args.report}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing report: {e}", file=sys.stderr)


def _handle_sitelog_subcommand(args, stations, url, log_level):
    """Handle site log generation subcommand."""
    # Initialize TOS client
    tos_client = TOSClient(base_url=url)  # Use default, respect centralized logging

    for station in stations:
        # Send status messages to stderr (but only when saving to file or multiple stations)
        if args.output or len(stations) > 1:
            print(f"Generating site log for station {station}", file=sys.stderr)

        try:
            # Get complete station metadata with proper device sessions (like legacy system)
            complete_station_data = tos_client.get_complete_station_metadata(station)
            if not complete_station_data:
                print(f"Error: Could not retrieve metadata for station {station}", file=sys.stderr)
                continue

            # Extract device sessions from complete metadata
            device_sessions = complete_station_data.get('device_history', [])

            # Generate site log
            site_log_content = generate_igs_site_log(
                complete_station_data, device_sessions, log_level.value
            )

            # Output handling - file vs stdout
            if args.output:
                # Write to specified file
                try:
                    with open(args.output, 'w', encoding='utf-8') as f:
                        f.write(site_log_content)
                    # Send success message to stderr to keep stdout clean
                    print(f"✓ Site log saved to {args.output}", file=sys.stderr)
                except Exception as e:
                    print(f"Error writing site log: {e}", file=sys.stderr)
            else:
                # Output to stdout (pipe-friendly)
                print(site_log_content)  # Clean output to stdout
                # Optional: Send completion notice to stderr (only for multiple stations)
                if len(stations) > 1:
                    print(f"✓ Site log for {station} completed", file=sys.stderr)

        except Exception as e:
            print(f"Error generating site log for {station}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
