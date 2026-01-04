# Toolbox

This repository is for one-off scripts, experimental code, and non-automated tools used for housekeeping and management.

## Key Projects

### 📸 Google Drive Photo Organization
Located in `/google-drive`, these tools were developed to reorganize large photo collections (like `QNAP831X`) into a chronological and event-based structure.

- **`discover_qnap.py`**: Recursively crawls a Drive folder and extracts deep metadata (EXIF, camera models, etc.).
- **`organize_qnap.py`**: Performs the live migration of files into the `YYYY/MM - [Event]` structure. Supports dry-runs by default.

## Structure

- `/google-drive`: Tools for managing Drive content.
- `/media`: Scripts for local media management.
- `/experiments`: Temporary or learning-related code.

## Usage

When you have a one-off task, ask Antigravity to create a script here, run it, and commit it if it's something you might need again.
