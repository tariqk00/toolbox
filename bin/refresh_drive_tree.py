"""
Crawls Google Drive folder structure from configured root IDs and writes
a flat path→ID map to config/drive_tree.json for use by the AI sorter.
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(current_dir))
if repo_root not in sys.path:
    sys.path.append(repo_root)

import json
import logging
from datetime import datetime, timezone

from toolbox.lib.drive_utils import get_drive_service, BASE_DIR, CONFIG_PATH

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("DriveTreeRefresh")

TREE_PATH = os.path.join(BASE_DIR, 'config', 'drive_tree.json')


def load_roots():
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        roots = config.get('roots', [])
        if not roots:
            logger.error("No 'roots' found in folder_config.json")
        return roots
    except Exception as e:
        logger.error(f"Error loading folder_config.json: {e}")
        return []


# Paths to exclude entirely (no crawl, not included in tree)
EXCLUDE_PREFIXES = [
    '05 - Media',
    '07 - Archive',
    '02 - Personal & ID/Kids/Soccer/Lindy',  # old Classic Sites attachment folders
    '03 - Finance/Taxes/2',                  # year subfolders (2003–2025)
]

# Paths where crawl stops at the listed depth
# depth is the number of '/' separators in the path
MAX_DEPTH = {
    '04 - Health/Fitness/Garmin': 3,      # keep Garmin/ but not year/month
    '04 - Health/Fitness/Trainheroic': 3,
}


def should_include(path):
    """Returns False if the path should be excluded from the tree."""
    for prefix in EXCLUDE_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def should_recurse(path):
    """Returns False if we should stop crawling children of this path."""
    depth = path.count('/')
    for prefix, max_depth in MAX_DEPTH.items():
        if path == prefix or path.startswith(prefix + '/'):
            return depth < max_depth
    return True


def crawl_folder(service, folder_id, folder_name, path_to_id, tree, depth=0):
    """Recursively crawls a folder, building path_to_id and tree."""
    if not should_include(folder_name):
        return

    path_to_id[folder_name] = folder_id
    tree[folder_name] = {"id": folder_id, "children": {}}

    if not should_recurse(folder_name):
        return

    try:
        page_token = None
        while True:
            query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            params = {
                "q": query,
                "fields": "nextPageToken, files(id, name)",
                "pageSize": 200,
            }
            if page_token:
                params["pageToken"] = page_token

            results = service.files().list(**params).execute()
            children = results.get('files', [])

            for child in children:
                child_path = f"{folder_name}/{child['name']}"
                crawl_folder(service, child['id'], child_path, path_to_id, tree[folder_name]["children"], depth + 1)

            page_token = results.get('nextPageToken')
            if not page_token:
                break

    except Exception as e:
        logger.error(f"  Error crawling '{folder_name}' ({folder_id}): {e}")


def get_root_name(service, folder_id):
    """Fetches the display name of a folder by ID."""
    try:
        res = service.files().get(fileId=folder_id, fields="name").execute()
        return res.get('name', folder_id)
    except Exception as e:
        logger.warning(f"  Could not fetch name for root {folder_id}: {e}. Using ID as name.")
        return folder_id


def main():
    logger.info("=== Drive Tree Refresh ===")

    roots = load_roots()
    if not roots:
        logger.error("No root IDs to crawl. Exiting.")
        sys.exit(1)

    logger.info(f"Connecting to Drive...")
    service = get_drive_service()

    path_to_id = {}
    tree = {}

    for root_id in roots:
        root_name = get_root_name(service, root_id)
        logger.info(f"Crawling root: {root_name} ({root_id})")
        crawl_folder(service, root_id, root_name, path_to_id, tree)

    output = {
        "refreshed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "path_to_id": path_to_id,
        "tree": tree,
    }

    with open(TREE_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"\nDone. Found {len(path_to_id)} folders across {len(roots)} roots.")
    logger.info(f"Written to: {TREE_PATH}")

    # Print top-level summary
    top_level = sorted(k for k in path_to_id if '/' not in k)
    logger.info(f"\nTop-level folders ({len(top_level)}):")
    for name in top_level:
        depth_count = sum(1 for k in path_to_id if k.startswith(name + '/'))
        logger.info(f"  {name}  ({depth_count} subfolders)")


if __name__ == "__main__":
    main()
