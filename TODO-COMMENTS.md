# TODO Comment System

This project uses a structured TODO comment system similar to [todo-comments.nvim](https://github.com/folke/todo-comments.nvim) for tracking critical points, bugs, improvements, and technical debt.

## Comment Types

### 🔥 **FIXME** - Critical bugs that need immediate attention
```python
# FIXME: Memory leak in GPS data processing loop
# FIXME: Authentication fails with special characters in station names
```

### 📋 **TODO** - Features and improvements to implement
```python
# TODO: Add support for RINEX 4.0 format
# TODO: Implement caching for TOS API responses
```

### 🚧 **HACK** - Temporary solutions that need proper implementation
```python
# HACK: Using hardcoded IMO contact info - should use API
# HACK: Manual column width calculation - needs dynamic sizing
```

### 🔍 **REVIEW** - Code sections that need architectural review
```python
# REVIEW: Contact management system is complex and needs refactoring
# REVIEW: Error handling strategy across API client classes
```

### ⚠️ **WARNING** - Important constraints and gotchas
```python
# WARNING: RINEX files require strict FORTRAN77 column formatting
# WARNING: This function modifies global state - not thread safe
```

### 💡 **NOTE** - Important information and context
```python
# NOTE: TOS API returns coordinates in WGS84 decimal degrees
# NOTE: Station names are case-insensitive in search but case-sensitive in display
```

### 🐛 **BUG** - Known issues that affect functionality
```python
# BUG: Date parsing fails for stations with missing start dates
# BUG: Unicode characters in station names break file exports
```

### ⚡ **PERF** - Performance optimization opportunities
```python
# PERF: Database queries could be batched for better performance
# PERF: Large RINEX files cause memory usage spikes
```

## Usage Guidelines

### 1. **Be Specific and Actionable**
```python
# Good
# TODO: Implement RINEX 3.05 header validation according to IGS standards

# Poor  
# TODO: Fix this
```

### 2. **Reference Issues and Documentation**
```python
# FIXME: Contact API timeout - see issue #123
# REVIEW: Logging architecture - documented in CLAUDE.md contact section
```

### 3. **Include Context and Impact**
```python
# HACK: Manual GPS time conversion - affects all timestamp calculations
# WARNING: Modifying this affects GAMIT processing compatibility
```

### 4. **Use Appropriate Priorities**
```python
# FIXME: Critical for production deployment
# TODO: Nice to have for v2.0
# PERF: Optimization for large datasets
```

## Current Critical Items

### High Priority
- `src/tostools/gps_metadata_qc.py:467` - **REVIEW**: Contact management architecture
- `src/tostools/io/rich_formatters.py:153` - **FIXME**: Group header alignment

### Medium Priority  
- `src/tostools/cli/main.py:175` - **TODO**: Add --no-static, --no-history flags
- `src/tostools/cli/main.py:176` - **TODO**: Detailed contact display

### Documentation Needed
- **WARNING**: RINEX FORTRAN77 formatting requirements throughout codebase
- **NOTE**: TOS API integration patterns and error handling

## Integration with Development Tools

### VS Code / Neovim
The comment patterns are compatible with:
- [Todo Tree](https://marketplace.visualstudio.com/items?itemName=Gruntfuggly.todo-tree) for VS Code
- [todo-comments.nvim](https://github.com/folke/todo-comments.nvim) for Neovim

### Git Hooks
Consider adding pre-commit hooks to:
- Scan for new FIXME comments before commits
- Generate TODO reports for release notes
- Validate comment format consistency

### CI Integration
- GitHub Actions can scan and report TODO comment statistics
- Track TODO debt over time in project metrics
- Block deploys with critical FIXME comments

## Best Practices

1. **Review TODOs regularly** - during sprint planning and code reviews
2. **Convert TODOs to issues** - for complex features requiring multiple commits  
3. **Remove completed TODOs** - clean up resolved items immediately
4. **Use consistent formatting** - follow the patterns above
5. **Link to external resources** - issues, documentation, RFCs when relevant

This system helps maintain code quality while providing clear visibility into technical debt and improvement opportunities.