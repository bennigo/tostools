# tostools Advanced Logging System

## Overview

The tostools project now includes a comprehensive, centralized logging system designed for professional GPS/GNSS station management. The system provides:

- **Multiple Output Formats**: Human-readable and structured JSON logging
- **Flexible Destinations**: Console, files, and level-specific file separation  
- **Centralized Configuration**: Consistent logging across all modules
- **Development & Production Modes**: Optimized configurations for different environments
- **Contextual Logging**: Rich metadata for operational analysis
- **Legacy Compatibility**: Seamless migration from existing logging patterns

## Quick Start

### Basic Console Logging
```python
from tostools.utils.logging import setup_console_logging, get_logger
import logging

# Setup console logging
setup_console_logging(level=logging.INFO)

# Get logger for your module
logger = get_logger(__name__)

# Log messages
logger.info("Processing GPS station data")
logger.warning("API response time exceeded threshold")
logger.error("Station validation failed")
```

### File Logging with Separation
```python
from tostools.utils.logging import setup_development_logging, get_logger

# Setup development logging (console + files + structured logs)
setup_development_logging(log_dir="logs")

logger = get_logger(__name__)
logger.debug("Debug info (files only)")
logger.info("Processing started (console + files)")
logger.error("Critical error (console + files + error-specific file)")
```

### Structured Logging for Analysis
```python
from tostools.utils.logging import configure_logging, LoggingConfig, get_logger

# Configure structured logging
configure_logging(LoggingConfig(
    console_level=logging.INFO,
    console_format="json",  # JSON format for programmatic analysis
    log_dir="logs",
    structured_file=True
))

logger = get_logger(__name__)

# Rich contextual logging
logger.info("GPS station processing started", extra={
    "station": "RHOF",
    "coordinates": {"lat": 66.461122, "lon": -15.946708},
    "operation": "site_log_generation",
    "user": "operator"
})
```

## tosGPS Integration

The main `tosGPS` command now includes comprehensive logging options:

### Command Line Options
```bash
# Basic usage with enhanced logging
tosGPS --debug-all PrintTOS RHOF

# Human-readable file logging
tosGPS --log-dir logs PrintTOS RHOF

# Structured JSON logging for analysis
tosGPS --log-dir logs --log-format json PrintTOS RHOF

# Production logging (less verbose)
tosGPS --log-dir /var/log/tostools --production-logging PrintTOS RHOF
```

### Example Output

#### Human-Readable Format
```
2025-08-23 07:21:20 | tostools.gps_metadata_qc | get_station_metadata | INFO | station RHOF id_entity: 4390
2025-08-23 07:21:20 | tostools.api.tos_client  | _make_request        | INFO | Sending request "https://vi-api.vedur.is:443/tos/v1/history/entity/4390/"
2025-08-23 07:21:21 | tostools.rinex.validator | compare_rinex_to_tos | WARNING | Minor discrepancy found in antenna height
```

#### Structured JSON Format
```json
{"timestamp": "2025-08-23T07:21:20.123456", "level": "INFO", "module": "tostools.gps_metadata_qc", "function": "get_station_metadata", "line": 178, "message": "station RHOF id_entity: 4390", "extra": {"station": "RHOF", "entity_id": 4390}}
{"timestamp": "2025-08-23T07:21:20.567890", "level": "WARNING", "module": "tostools.rinex.validator", "function": "compare_rinex_to_tos", "line": 89, "message": "Minor discrepancy found", "extra": {"field": "antenna_height", "expected": "0.000", "actual": "-0.007"}}
```

## Configuration Options

### LoggingConfig Class
```python
from tostools.utils.logging import LoggingConfig, configure_logging

config = LoggingConfig(
    console_level=logging.INFO,        # Console verbosity
    file_level=logging.DEBUG,          # File verbosity
    log_dir="logs",                    # Log directory (None = no files)
    console_format="human",            # "human" or "json"
    file_format="human",               # "human" or "json" 
    structured_file=True,              # Create separate JSON log
    separate_levels=True,              # Create files per level
    max_file_size=10*1024*1024,       # 10MB file rotation
    backup_count=5                     # Keep 5 backup files
)

configure_logging(config)
```

### File Structure
When file logging is enabled with `separate_levels=True`:

```
logs/
├── tostools.log              # Main log (all levels)
├── tostools_structured.jsonl # JSON structured log
├── tostools_error.log        # Error messages only
├── tostools_warning.log      # Warning messages only  
├── tostools_info.log         # Info messages only
└── tostools_debug.log        # Debug messages only
```

## Contextual Logging

### Station Processing Context
```python
# Logger with persistent context for GPS operations
gps_logger = get_logger(__name__, extra_context={
    "session_id": "gps_session_001",
    "station": "RHOF",
    "operation": "rinex_validation"
})

# All log messages automatically include context
gps_logger.info("Starting validation")
gps_logger.warning("Discrepancy detected", extra={"field": "antenna_height"})
gps_logger.info("Validation completed", extra={"status": "success"})
```

### TOS API Logging
```python
# Rich API interaction logging
logger.info("TOS API call started", extra={
    "endpoint": "/history/entity/4390/",
    "station": "RHOF",
    "method": "GET",
    "timeout": 10
})

logger.warning("API slow response", extra={
    "response_time_ms": 2500,
    "threshold_ms": 2000,
    "retry_attempt": 1
})
```

## Convenience Functions

### Development Logging
```python
from tostools.utils.logging import setup_development_logging

# Optimized for development: DEBUG level files, INFO console, all features enabled
setup_development_logging(log_dir="logs")
```

### Production Logging  
```python
from tostools.utils.logging import setup_production_logging

# Optimized for production: WARNING console, INFO files, JSON format, larger files
setup_production_logging(log_dir="/var/log/tostools")
```

### Console Only
```python
from tostools.utils.logging import setup_console_logging

# Simple console-only logging
setup_console_logging(level=logging.INFO)
```

## Migration from Legacy Logging

### Old Pattern
```python
# Old fragmented approach
import logging
from tostools.metadata_functions import get_logger

module_logger = get_logger(__name__, loglevel=logging.WARNING)
module_logger.info("Message")
```

### New Pattern
```python
# New centralized approach
from tostools.utils.logging import get_logger

logger = get_logger(__name__)
logger.info("Message")
```

### Legacy Compatibility
The system includes compatibility functions:
```python
# This still works for existing code
from tostools.utils.logging import get_tostools_logger

logger = get_tostools_logger(__name__, loglevel=logging.WARNING)
```

## Best Practices

### 1. Use Structured Context
```python
# Good: Rich context for analysis
logger.info("Station processing completed", extra={
    "station": "RHOF",
    "duration_seconds": 45.2,
    "devices_processed": 3,
    "discrepancies_found": 0
})

# Avoid: Generic messages
logger.info("Processing completed")
```

### 2. Appropriate Log Levels
```python
# DEBUG: Detailed diagnostic information
logger.debug("RINEX header field parsed", extra={"field": "MARKER NAME", "value": "RHOF"})

# INFO: General operational information  
logger.info("Site log generation started", extra={"station": "RHOF"})

# WARNING: Unexpected but recoverable conditions
logger.warning("API timeout, retrying", extra={"attempt": 2, "max_attempts": 3})

# ERROR: Error conditions that affect functionality
logger.error("Station validation failed", extra={"station": "RHOF", "errors": ["missing_coordinates"]})
```

### 3. Module-Specific Loggers
```python
# Each module gets its own logger
class TOSClient:
    def __init__(self):
        self.logger = get_logger(__name__)  # tostools.api.tos_client
    
    def search_stations(self, station):
        self.logger.info("Searching for station", extra={"station": station})
```

## Log Analysis Examples

### Find All Errors
```bash
# Human-readable logs
grep "ERROR" logs/tostools_error.log

# Structured logs  
jq -r 'select(.level=="ERROR") | .message' logs/tostools_structured.jsonl
```

### Station Processing Analysis
```bash
# Find all operations for specific station
jq -r 'select(.extra.station=="RHOF") | "\(.timestamp) \(.level) \(.message)"' logs/tostools_structured.jsonl

# Performance analysis
jq -r 'select(.extra.response_time_ms) | "\(.extra.station) \(.extra.response_time_ms)ms"' logs/tostools_structured.jsonl
```

### Error Rate Analysis
```bash
# Count errors by module
jq -r 'select(.level=="ERROR") | .module' logs/tostools_structured.jsonl | sort | uniq -c

# Find slow operations
jq -r 'select(.extra.response_time_ms > 2000) | "\(.timestamp) \(.extra.station) \(.extra.response_time_ms)ms"' logs/tostools_structured.jsonl
```

## Integration with Monitoring Systems

### Logstash/Elasticsearch
```json
{
  "timestamp": "2025-08-23T07:21:20.123456",
  "level": "ERROR", 
  "module": "tostools.rinex.validator",
  "message": "RINEX validation failed",
  "extra": {
    "station": "RHOF",
    "file": "RHOF0790.02D", 
    "errors": ["antenna_height_mismatch"],
    "expected_height": "0.000",
    "actual_height": "-0.007"
  }
}
```

### Prometheus/Grafana Metrics
Use structured logs to generate metrics:
```python
# Log with metrics-friendly structure
logger.info("operation_completed", extra={
    "operation_type": "site_log_generation",
    "station": "RHOF", 
    "duration_seconds": 12.4,
    "success": True
})
```

## Configuration Files

### Development Config (tostools-dev-logging.json)
```json
{
    "console_level": "INFO",
    "file_level": "DEBUG", 
    "log_dir": "logs",
    "console_format": "human",
    "file_format": "human",
    "structured_file": true,
    "separate_levels": true
}
```

### Production Config (tostools-prod-logging.json)  
```json
{
    "console_level": "WARNING",
    "file_level": "INFO",
    "log_dir": "/var/log/tostools", 
    "console_format": "human",
    "file_format": "json",
    "structured_file": true,
    "separate_levels": true,
    "max_file_size": 52428800,
    "backup_count": 10
}
```

## Troubleshooting

### No Log Files Created
- Ensure log directory has write permissions
- Check that `log_dir` parameter is provided
- Verify logging configuration is applied: `logging.getLogger().handlers`

### Performance Impact
- Use appropriate log levels (avoid DEBUG in production)
- Consider async logging for high-volume scenarios
- Monitor file system space with log rotation

### JSON Format Issues
- Ensure all logged objects are JSON-serializable
- Use `default=str` in custom JSON encoders for datetime objects
- Validate JSON structure with `jq` or similar tools

---

## Summary

The new logging system provides enterprise-grade logging capabilities while maintaining simplicity for basic use cases. It supports both human operators performing GPS station maintenance and automated systems requiring structured log analysis.

Key benefits:
- **Centralized Configuration**: No more scattered logging setup across modules  
- **Rich Context**: Structured metadata for operational intelligence
- **Flexible Output**: Human-readable and machine-parseable formats
- **Production Ready**: File rotation, level separation, performance optimization
- **Legacy Compatible**: Smooth migration path for existing code

For questions or enhancements, contact the tostools development team.