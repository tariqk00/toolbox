"""
Google Tasks API helper.
Auth uses toolbox/config/token_tasks.json (separate from Drive/Gmail tokens).
Run `python3 -m toolbox.lib.tasks --auth` once to authorize.
"""
import logging
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TASKS_SCOPES = ['https://www.googleapis.com/auth/tasks']
TOKEN_PATH = BASE_DIR / 'config' / 'token_tasks.json'

logger = logging.getLogger('Tasks')


def get_tasks_service():
    from toolbox.lib.google_api import GoogleAuth
    auth = GoogleAuth(base_dir=str(BASE_DIR))
    creds = auth.get_credentials(
        token_filename='token_tasks.json',
        credentials_filename='config/credentials.json',
        scopes=TASKS_SCOPES,
    )
    from googleapiclient.discovery import build
    return build('tasks', 'v1', credentials=creds)


def get_or_create_list(service, name: str) -> str:
    """Return task list ID for the named list, creating it if needed."""
    result = service.tasklists().list(maxResults=100).execute()
    for tl in result.get('items', []):
        if tl['title'] == name:
            return tl['id']
    new_list = service.tasklists().insert(body={'title': name}).execute()
    logger.info(f'Created task list: {name}')
    return new_list['id']


def create_task(service, list_id: str, title: str, due: str = None, notes: str = None) -> dict:
    """
    Create a task in the given list.
    due: ISO date string YYYY-MM-DD, or None.
    notes: plain text notes/context.
    """
    body = {'title': title, 'status': 'needsAction'}
    if due:
        body['due'] = f'{due}T00:00:00.000Z'
    if notes:
        body['notes'] = notes
    task = service.tasks().insert(tasklist=list_id, body=body).execute()
    logger.info(f'Created task: {title[:60]} (due: {due or "none"})')
    return task


if __name__ == '__main__':
    if '--auth' in sys.argv:
        print('Authorizing Google Tasks...')
        svc = get_tasks_service()
        lists = svc.tasklists().list().execute()
        print('Auth successful. Existing task lists:')
        for tl in lists.get('items', []):
            print(f'  - {tl["title"]}')
    else:
        print('Usage: python3 -m toolbox.lib.tasks --auth')
