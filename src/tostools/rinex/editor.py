"""
RINEX file editing and header correction utilities.

This module provides functions for editing RINEX headers based on TOS metadata
and fixing common RINEX file issues.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.logging import get_logger


def fix_rinex_header(rinex_content: str, 
                    corrections: Dict[str, str],
                    loglevel: int = logging.WARNING) -> str:
    """
    Apply corrections to RINEX header content.
    
    Args:
        rinex_content: Original RINEX file content
        corrections: Dictionary of corrections {field_name: new_value}
        loglevel: Logging level
        
    Returns:
        Corrected RINEX content
    """
    logger = get_logger(__name__, loglevel)
    
    lines = rinex_content.split('\n')
    corrected_lines = []
    corrections_applied = 0
    
    for line in lines:
        modified_line = line
        
        # Check each correction
        for field_name, new_value in corrections.items():
            if field_name in line:
                # Extract the current value part (before the field name)
                field_pos = line.find(field_name)
                if field_pos > 0:
                    # Keep the original formatting but replace the value
                    prefix = new_value.ljust(field_pos)[:field_pos]
                    suffix = line[field_pos:]
                    modified_line = prefix + suffix
                    corrections_applied += 1
                    logger.debug(f"Applied correction to {field_name}")
                break
        
        corrected_lines.append(modified_line)
        
        # Stop at end of header
        if "END OF HEADER" in line:
            # Add remaining lines unchanged
            remaining_idx = lines.index(line) + 1
            corrected_lines.extend(lines[remaining_idx:])
            break
    
    logger.info(f"Applied {corrections_applied} corrections to RINEX header")
    return '\n'.join(corrected_lines)


def fix_rinex_line(field_name: str, 
                  correction_value: str, 
                  original_line: str,
                  loglevel: int = logging.WARNING) -> str:
    """
    Fix a specific RINEX header line.
    
    Args:
        field_name: RINEX field name (e.g., "MARKER NAME")
        correction_value: New value for the field
        original_line: Original header line
        loglevel: Logging level
        
    Returns:
        Corrected header line
    """
    logger = get_logger(__name__, loglevel)
    
    if field_name not in original_line:
        logger.warning(f"Field '{field_name}' not found in line")
        return original_line
    
    # Find field position
    field_pos = original_line.find(field_name)
    
    # Apply standard RINEX formatting based on field type
    if field_name == "MARKER NAME":
        # 60 characters for marker name
        new_line = f"{correction_value:<60}{original_line[60:]}"
    elif field_name == "MARKER NUMBER":
        # 20 characters for marker number
        new_line = f"{correction_value:<20}{original_line[20:]}"
    elif field_name == "OBSERVER / AGENCY":
        # 20 characters each for observer and agency
        parts = correction_value.split(' ', 1)
        observer = parts[0] if parts else ""
        agency = parts[1] if len(parts) > 1 else ""
        new_line = f"{observer:<20}{agency:<20}{original_line[40:]}"
    elif field_name == "REC # / TYPE / VERS":
        # 20 characters each for serial, type, version
        parts = correction_value.split()
        serial = parts[0] if len(parts) > 0 else ""
        model = parts[1] if len(parts) > 1 else ""
        version = ' '.join(parts[2:]) if len(parts) > 2 else ""
        new_line = f"{serial:<20}{model:<20}{version:<20}{original_line[60:]}"
    elif field_name == "ANT # / TYPE":
        # 20 characters each for serial and type
        parts = correction_value.split(' ', 1)
        serial = parts[0] if parts else ""
        ant_type = parts[1] if len(parts) > 1 else ""
        new_line = f"{serial:<20}{ant_type:<20}{original_line[40:]}"
    elif field_name == "ANTENNA: DELTA H/E/N":
        # 14.4 format for each coordinate
        coords = correction_value.split()
        if len(coords) >= 3:
            h = float(coords[0])
            e = float(coords[1])
            n = float(coords[2])
            new_line = f"{h:14.4f}{e:14.4f}{n:14.4f}{original_line[42:]}"
        else:
            new_line = original_line
    else:
        # Generic replacement - preserve field position
        new_line = f"{correction_value:<{field_pos}}{original_line[field_pos:]}"
    
    logger.debug(f"Fixed line for {field_name}")
    return new_line


def update_rinex_files(file_paths: List[Union[str, Path]], 
                      corrections_list: List[Dict[str, str]],
                      backup: bool = True,
                      loglevel: int = logging.WARNING) -> Dict[str, bool]:
    """
    Update multiple RINEX files with corrections.
    
    Args:
        file_paths: List of RINEX file paths
        corrections_list: List of correction dictionaries (one per file)
        backup: Whether to create backup files
        loglevel: Logging level
        
    Returns:
        Dictionary mapping file paths to success status
    """
    logger = get_logger(__name__, loglevel)
    
    results = {}
    
    for file_path, corrections in zip(file_paths, corrections_list):
        path = Path(file_path)
        
        try:
            # Read original file
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()
            
            # Apply corrections
            corrected_content = fix_rinex_header(original_content, corrections, loglevel)
            
            # Create backup if requested
            if backup:
                backup_path = path.with_suffix(path.suffix + '.backup')
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                logger.info(f"Created backup: {backup_path}")
            
            # Write corrected file
            with open(path, 'w', encoding='utf-8') as f:
                f.write(corrected_content)
            
            results[str(path)] = True
            logger.info(f"Successfully updated {path}")
            
        except Exception as e:
            logger.error(f"Failed to update {path}: {e}")
            results[str(path)] = False
    
    success_count = sum(results.values())
    logger.info(f"Successfully updated {success_count}/{len(file_paths)} files")
    
    return results


def validate_rinex_format(file_content: str, 
                         loglevel: int = logging.WARNING) -> Dict[str, List[str]]:
    """
    Validate RINEX file format and structure.
    
    Args:
        file_content: RINEX file content
        loglevel: Logging level
        
    Returns:
        Dictionary of validation issues by category
    """
    logger = get_logger(__name__, loglevel)
    
    issues = {
        "format_errors": [],
        "missing_required": [],
        "warnings": []
    }
    
    lines = file_content.split('\n')
    
    # Check for basic structure
    if not any("RINEX VERSION / TYPE" in line for line in lines):
        issues["format_errors"].append("Missing RINEX VERSION / TYPE header")
    
    if not any("END OF HEADER" in line for line in lines):
        issues["format_errors"].append("Missing END OF HEADER marker")
    
    # Check required fields
    required_fields = [
        "MARKER NAME",
        "OBSERVER / AGENCY",
        "REC # / TYPE / VERS",
        "ANT # / TYPE"
    ]
    
    header_lines = []
    for line in lines:
        header_lines.append(line)
        if "END OF HEADER" in line:
            break
    
    header_content = '\n'.join(header_lines)
    
    for field in required_fields:
        if field not in header_content:
            issues["missing_required"].append(field)
    
    # Check line length consistency
    for i, line in enumerate(header_lines[:-1]):  # Exclude END OF HEADER
        if len(line) > 80:
            issues["warnings"].append(f"Line {i+1} exceeds 80 characters")
        elif len(line) < 60 and line.strip():  # Skip empty lines
            issues["warnings"].append(f"Line {i+1} shorter than expected")
    
    # Check version format
    version_line = next((line for line in header_lines if "RINEX VERSION / TYPE" in line), None)
    if version_line:
        version_part = version_line[:20].strip()
        if not re.match(r'^\d+\.\d+', version_part):
            issues["format_errors"].append("Invalid RINEX version format")
    
    total_issues = sum(len(issue_list) for issue_list in issues.values())
    logger.info(f"RINEX format validation found {total_issues} issues")
    
    return issues


def standardize_rinex_header(file_content: str, 
                           station_info: Dict[str, Any],
                           loglevel: int = logging.WARNING) -> str:
    """
    Standardize RINEX header according to IGS conventions.
    
    Args:
        file_content: Original RINEX content
        station_info: Station information for standardization
        loglevel: Logging level
        
    Returns:
        Standardized RINEX content
    """
    logger = get_logger(__name__, loglevel)
    
    lines = file_content.split('\n')
    standardized_lines = []
    
    # Process each line in the header
    for line in lines:
        new_line = line
        
        # Standardize marker name (uppercase, no spaces)
        if "MARKER NAME" in line:
            marker = station_info.get("marker", "").upper().replace(" ", "")
            new_line = f"{marker:<60}MARKER NAME"
        
        # Standardize observer/agency
        elif "OBSERVER / AGENCY" in line:
            contact = station_info.get("contact", {})
            agency = contact.get("owner", {}).get("abbreviation", "UNKNOWN")
            new_line = f"{'GNSS OPERATOR':<20}{agency:<20}{'OBSERVER / AGENCY'}"
        
        # Ensure consistent formatting
        elif any(field in line for field in ["REC # / TYPE / VERS", "ANT # / TYPE"]):
            # Keep existing content but ensure proper spacing
            field_name = next(field for field in ["REC # / TYPE / VERS", "ANT # / TYPE"] if field in line)
            content_part = line[:line.find(field_name)].rstrip()
            new_line = f"{content_part:<60}{field_name}"
        
        standardized_lines.append(new_line)
        
        if "END OF HEADER" in line:
            # Add remaining lines unchanged
            remaining_idx = lines.index(line) + 1
            standardized_lines.extend(lines[remaining_idx:])
            break
    
    logger.info("Applied RINEX header standardization")
    return '\n'.join(standardized_lines)