#!python

import argparse

from argparse_logging import add_log_level_argument

from . import gps_metadata_functions as gpsf
from . import gps_metadata_qc as gpsqc

# Import new modular components
from .api.tos_client import TOSClient
from .core.site_log import generate_igs_site_log
from .rinex.editor import update_rinex_files
from .rinex.reader import extract_header_info, read_rinex_header
from .rinex.validator import compare_rinex_to_tos


def main():
    """
    quering metadata from tos and comparing to relevant rinex files
    """

    # logging settings
    # logger = get_logger(name=__name__, level=logging.DEBUG)

    url_rest_tos = "vi-api.vedur.is/tos/v1"
    stationInfo_list = []

    # print(module_logger.getEffectiveLevel())

    parser = argparse.ArgumentParser(
        description="QC tool to manage GPS medata through TOS",
        epilog="For any issues regarding this program or the GPS"
        + "system contact, Benni,  email: bgo@vedur.is,"
        + "or Hildur email: hildur@vedur.is",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    add_log_level_argument(parser)

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
        "PrintTOS", help="Choose beteween printing options of TOS metadata"
    )
    print_options.add_argument("stations", nargs="+", help="List of stations")
    print_options.add_argument(
        "-f",
        "--format",
        choices=["table", "gamit"],
        default="table",
        help="Print raw format as",
    )
    print_options.add_argument("--raw", action="store_true", help="Print raw format")

    # RINEX validation subcommand
    rinex_parser = subparsers.add_parser(
        "rinex", help="RINEX file validation and correction"
    )
    rinex_parser.add_argument("stations", nargs="+", help="List of stations")
    rinex_parser.add_argument(
        "rinex_files", nargs="+", help="RINEX files to validate"
    )
    rinex_parser.add_argument(
        "--fix", action="store_true", help="Apply corrections to RINEX files"
    )
    rinex_parser.add_argument(
        "--backup", action="store_true", help="Create backup files when fixing"
    )
    rinex_parser.add_argument(
        "--report", type=str, help="Generate QC report to specified file"
    )

    # Site log generation subcommand
    sitelog_parser = subparsers.add_parser(
        "sitelog", help="Generate IGS site log"
    )
    sitelog_parser.add_argument("stations", nargs="+", help="List of stations")
    sitelog_parser.add_argument(
        "--output", "-o", type=str, help="Output file for site log"
    )

    args = parser.parse_args()
    stations = getattr(args, 'stations', [])
    # Constructing the URL:
    url = "{}://{}:{}{}".format(args.protocol, args.server, args.port, args.rest)
    log_level = args.log_level

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
        (args.format, args.raw) if args.subcommand == "PrintTOS" else ("table", False)
    )

    for sta in stations:
        station_info = gpsqc.gps_metadata(sta, url, loglevel=log_level.value)
        if pformat == "table":
            gpsf.print_station_history(
                station_info, raw_format=raw, loglevel=log_level.value
            )
        elif pformat == "gamit":
            stationInfo_list += gpsf.print_station_history(station_info)

    stationInfo_list.sort()
    for infoline in stationInfo_list:
        print(infoline)


def _handle_rinex_subcommand(args, stations, url, log_level):
    """Handle RINEX validation and correction subcommand."""
    from pathlib import Path

    print(f"RINEX QC for stations: {', '.join(stations)}")

    # Initialize TOS client
    tos_client = TOSClient(base_url=url, loglevel=log_level.value)

    all_comparisons = []

    for station in stations:
        print(f"\n=== Processing station {station} ===")

        # Get station metadata using legacy system (more reliable for validation)
        try:
            station_data = gpsqc.gps_metadata(station, url, loglevel=log_level.value)
            if not station_data:
                print(f"Error: Could not retrieve metadata for station {station}")
                continue

            # Extract device sessions for validation (use most recent)
            device_sessions = station_data.get('device_history', [])
            if not device_sessions:
                print(f"Warning: No device history found for station {station}")
                continue

            # Use the most recent session for validation
            current_session = device_sessions[-1]

        except Exception as e:
            print(f"Error retrieving station data: {e}")
            continue

        # Validate each RINEX file
        for rinex_file in args.rinex_files:
            rinex_path = Path(rinex_file)
            if not rinex_path.exists():
                print(f"Warning: RINEX file {rinex_file} not found")
                continue

            print(f"\nValidating RINEX file: {rinex_file}")

            # Read RINEX header
            header_data = read_rinex_header(rinex_path, log_level.value)
            if not header_data:
                print(f"Error reading RINEX header from {rinex_file}")
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
                print(f"Found {len(comparison['discrepancies'])} discrepancies:")
                for field, diff in comparison['discrepancies'].items():
                    print(f"  {field}: RINEX='{diff.get('rinex', '')}' vs TOS='{diff.get('tos', '')}'")
            else:
                print("✓ No discrepancies found")

            # Apply fixes if requested
            if args.fix and comparison.get("corrections"):
                print(f"Applying {len(comparison['corrections'])} corrections...")
                success = update_rinex_files(
                    [rinex_path],
                    [comparison['corrections']],
                    backup=args.backup,
                    loglevel=log_level.value
                )
                if success.get(str(rinex_path)):
                    print("✓ Corrections applied successfully")
                else:
                    print("✗ Failed to apply corrections")

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
            print(f"\n✓ QC report saved to {args.report}")
        except Exception as e:
            print(f"Error writing report: {e}")


def _handle_sitelog_subcommand(args, stations, url, log_level):
    """Handle site log generation subcommand."""
    # Initialize TOS client
    tos_client = TOSClient(base_url=url, loglevel=log_level.value)

    for station in stations:
        print(f"Generating site log for station {station}")

        try:
            # Get complete station metadata with proper device sessions (like legacy system)
            complete_station_data = tos_client.get_complete_station_metadata(station)
            if not complete_station_data:
                print(f"Error: Could not retrieve metadata for station {station}")
                continue

            # Extract device sessions from complete metadata
            device_sessions = complete_station_data.get('device_history', [])

            # Generate site log
            site_log_content = generate_igs_site_log(
                complete_station_data, device_sessions, log_level.value
            )

            # Output handling
            if args.output:
                output_file = args.output
            else:
                marker = complete_station_data.get('marker', station).upper()
                output_file = f"{marker}_sitelog.txt"

            # Write to file
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(site_log_content)
                print(f"✓ Site log saved to {output_file}")
            except Exception as e:
                print(f"Error writing site log: {e}")

        except Exception as e:
            print(f"Error generating site log for {station}: {e}")


if __name__ == "__main__":
    main()
