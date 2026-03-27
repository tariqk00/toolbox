# Toolbox Tasks

- [x] [Refactor] Centralize hardcoded folder IDs into `config/folder_config.json`
- [x] [Fix] Correct `RECOMMENDATIONS_PATH` in `monthly_review.py` (was pointing to `google-drive/`, now `config/`)
- [x] [Chore] Create `bin/__init__.py` with `setup_path()` helper
- [x] [Chore] Archive one-off folder-creation scripts to `bin/archive/`
- [x] [Feature] Consolidate history to `_Master_Archive_Metadata` & Enhance CSV (v0.4.0)
- [x] [Dev] Enable local testing environment (Secrets + Test Suite)
- [ ] [Maintenance] Regular audit of Google Drive scripts
- [ ] [Refactor] Update active `bin/` scripts to use `setup_path()` from `bin/__init__.py` (reduces boilerplate)
- [ ] [Refactor] Archive or remove obsolete diagnostic scripts in `bin/` (list_nested_plaud.py, list_pkm_ids.py, list_subfolder_contents.py, group_plaud_files.py)
- [ ] [Feature] Migrate History Log to Google Sheets (Scopes + Migration)
- [ ] [Documentation] Update `drive_organizer.py` docstrings
