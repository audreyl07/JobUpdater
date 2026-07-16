# JobUpdater

JobUpdater is a Python-based job scanning tool that loads company configurations, runs scanner implementations for each company, filters the collected jobs, and prints a summary to the console.

## Features

- Loads company configuration from a YAML file
- Loads filter rules from a YAML file
- Runs scanner implementations per company
- Filters jobs before displaying results
- Outputs a scan summary and accepted job links

## Usage

```bash
python main.py --config config/companies.yaml --filters config/filters.yaml
```

### Optional arguments

- `--config`: Path to the companies configuration file
- `--filters`: Path to the filters configuration file
- `--page-size`: Page size used by scanners
- `--timeout`: Request timeout in seconds

## Example

```bash
python main.py --page-size 20 --timeout 30
```

## Project structure

- `main.py` — CLI entry point
- `app/config` — configuration loading
- `app/filters` — job filtering logic
- `app/scanners` — scanner implementations
- `app/utils` — shared utilities such as logging

## Technologies used

- **Python**
- **argparse** for command-line parsing
- **pathlib** for file path handling
- **YAML configuration files**
- **Custom application modules** for config loading, scanning, filtering, and logging
- **Logging** via a shared logger utility

## Notes

The active code shows a `workday` scanner implementation, so the project appears to be built around modular source-specific scanners.