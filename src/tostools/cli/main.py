"""
Main CLI interface for tosGPS - Pure UI logic layer.

This module provides a clean command-line interface that delegates
all business logic to the appropriate modular components.
"""

import argparse
import logging
import sys
from typing import List, Optional

from ..utils.logging import get_logger
from ..core.station import Station
from ..api.tos_client import TOSClient
from ..io.formatters import json_print


def setup_argument_parser() -> argparse.ArgumentParser:
    """
    Set up command line argument parser for tosGPS.
    
    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog='tosGPS',
        description='GPS metadata quality control and station management tool',
        epilog='For more information, visit: https://github.com/bennigo/tostools'
    )
    
    parser.add_argument(
        'stations',
        nargs='+',
        help='Station identifiers to process'
    )
    
    parser.add_argument(
        'action',
        nargs='?',
        default='PrintTOS',
        choices=['PrintTOS', 'rinex'],
        help='Action to perform (default: PrintTOS)'
    )
    
    parser.add_argument(
        '--server',
        default='vi-api.vedur.is',
        help='TOS server hostname (default: vi-api.vedur.is)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=443,
        help='TOS server port (default: 443)'
    )
    
    parser.add_argument(
        '--format',
        choices=['table', 'json', 'raw'],
        default='table',
        help='Output format (default: table)'
    )
    
    parser.add_argument(
        '--raw',
        action='store_true',
        help='Use raw format (equivalent to --format raw)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Debug output'
    )
    
    return parser


def determine_log_level(args: argparse.Namespace) -> int:
    """
    Determine logging level based on command line arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Logging level constant
    """
    if args.debug:
        return logging.DEBUG
    elif args.verbose:
        return logging.INFO
    else:
        return logging.WARNING


def build_tos_url(server: str, port: int) -> str:
    """
    Build TOS API URL from server and port.
    
    Args:
        server: Server hostname
        port: Server port
        
    Returns:
        Complete TOS API URL
    """
    protocol = 'https' if port == 443 else 'http'
    return f"{protocol}://{server}:{port}/tos/v1"


def process_stations(
    station_ids: List[str], 
    tos_client: TOSClient, 
    output_format: str, 
    raw_format: bool,
    loglevel: int
) -> None:
    """
    Process station data and display results.
    
    Args:
        station_ids: List of station identifiers
        tos_client: TOS API client instance
        output_format: Output format ('table', 'json', 'raw')
        raw_format: Whether to use raw format
        loglevel: Logging level
    """
    logger = get_logger(__name__, loglevel)
    
    for station_id in station_ids:
        logger.info(f"Processing station: {station_id}")
        
        try:
            # Use the GPS metadata function to get station data
            from .. import gps_metadata_qc
            
            # Get station data using the GPS metadata function
            station_data = gps_metadata_qc.gps_metadata(station_id, tos_client.base_url, loglevel)
            
            if not station_data:
                logger.warning(f"No data found for station: {station_id}")
                continue
            
            # Display results based on format
            if output_format == 'json':
                print(json_print(station_data))
            else:
                # Use the existing print_station_history function for table/raw format
                from .. import gps_metadata_functions
                use_raw = raw_format or (output_format == 'raw')
                gps_metadata_functions.print_station_history(station_data, raw_format=use_raw, loglevel=loglevel)
                
        except Exception as e:
            logger.error(f"Error processing station {station_id}: {e}")
            if loglevel <= logging.DEBUG:
                import traceback
                traceback.print_exc()


def main_cli() -> int:
    """
    Main CLI entry point.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # Determine logging level
    loglevel = determine_log_level(args)
    logger = get_logger(__name__, loglevel)
    
    # Handle format arguments
    output_format = 'raw' if args.raw else args.format
    
    try:
        # Build TOS client
        tos_url = build_tos_url(args.server, args.port)
        tos_client = TOSClient(base_url=tos_url, loglevel=loglevel)
        
        logger.info(f"Using TOS API: {tos_url}")
        logger.info(f"Processing {len(args.stations)} stations: {', '.join(args.stations)}")
        
        # Process stations based on action
        if args.action == 'rinex':
            logger.info("RINEX processing not yet implemented in modular CLI")
            print("RINEX functionality is available via the legacy interface")
            return 1
        else:  # PrintTOS
            process_stations(
                args.stations, 
                tos_client, 
                output_format, 
                args.raw,
                loglevel
            )
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if loglevel <= logging.DEBUG:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main_cli())