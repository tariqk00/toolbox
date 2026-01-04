---
description: Standard workflow for organizing any Google Drive folders with 3-tier archiving.
---

# Google Drive File Organization Workflow

Follow these steps for any new photo/video organization project to ensure consistency and proper record-keeping.

## 1. Deep Discovery
1.  Identify target folder in Google Drive.
2.  Run a recursive metadata analyzer to fetch:
    -   File types and counts.
    -   Creation/Modification dates.
    -   EXIF data (for photos/videos).
    -   Folder-naming patterns.
    -   System file counts.
3.  Save the results to a JSON file for analysis.

## 2. Planning & Strategy
1.  Present an analysis report to the user.
2.  Propose a structural mapping using the **`YYYY/MM - [Event Name]`** pattern.
3.  **Core Principal**: Preserve original descriptive folder names as the "Event" context.
4.  Generate a preview for user approval.

## 3. Migration
1.  Refine the migration script (`organize_qnap.py`) for the specific folder.
2.  **Always Perform a Dry Run** first and log the output.
3.  Obtain necessary Drive Scope authorization.
4.  Execute Migration and monitor progress (log to local `.txt` file).

## 4. 3-Tier Archiving (Crucial)
To ensure privacy and permanence, every project must follow this archiving scheme:

1.  **GitHub tier**: Commit the specific discovery and migration scripts to the `toolbox` repository.
2.  **Master Archive tier**: Upload the Implementation Plan, Project Walkthrough, and Analysis Report to the `_Master_Archive_Metadata` folder at the root of the user's Google Drive.
3.  **Local Manifest tier**: Generate a final structure snapshot and save it as `_ORGANIZATION_RECORD.md` directly INSIDE the newly organized folder on Google Drive.

## 5. Cleanup
-   Remove temporary JSON analysis files and log files from the local workspace.
-   Ensure the `token_full_drive.json` is ignored by git.
