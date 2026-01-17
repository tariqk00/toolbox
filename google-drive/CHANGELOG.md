# Changelog - AI Drive Sorter

All notable changes to this project will be documented in this file.

## [0.4.2] - 2026-01-17

### Fixed

- **MIME Type Validation**: Implemented strict whitelist to skip unsupported binary formats (`.mdi`, `.xls`, `.mny`, `.pptx`) and prevent Gemini 400 errors.
- **Resilient Naming**: Updated name generation to preserve original filenames on AI failure or unsupported formats.
- **Move Logic Hardening**: Fixed a `NoneType` error when moving files without parent metadata.
- **Recovery Success**: Reverted 25 files corrupted by "AI Error" renames using historical logs.

## [0.4.1] - 2026-01-17

### Added

- **Hybrid Logging**: Local `RotatingFileHandler` (1MB max, 5 backups) in `logs/sorter.log`.
- **Drive Sync**: Automatic mirror of local logs to `Metadata/Logs/sorter.log` on Google Drive.
- **Versioned Logging**: Run start messages now include the script version for audit trails.

### Removed

- Legacy `Run_Logs` Google Sheets tab (replaced by text logs for performance).

## [0.4.0] - 2026-01-17

### Added

- **Operational Logging**: High-level run tracking (Processed, Moved, Renamed, Errors).
- **Run Summaries**: Single-line summaries for efficient monitoring.

## [0.3.0] - 2026-01-16

### Changed

- **History Migration**: Moved transformation history from `renaming_history.csv` to Google Sheets.
- **Clickable Hyperlinks**: Integrated Sheet formulas for one-click access to files and folders.

## [0.2.0] - 2026-01-16

### Fixed

- **Full Path Resolution**: Recursive API lookups now resolve full folder paths (e.g., `My Drive / 03 - Finance`).
- **Quote Escaping**: Fixed Sheets formula errors caused by special characters in filenames.

## [0.1.0] - 2026-01-02

### Added

- **Initial Release**: Core AI-driven file renaming and Inbox-to-Target movement.
- **Systemd Timers**: Hourly automation setup on NUC.
