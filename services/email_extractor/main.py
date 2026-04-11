"""
Email extraction pipeline — daily Gmail scan → 01 - Second Brain/Memory/ in Drive.

First run (no state file): in:inbox + all emails from today (incl. archived/deleted).
Subsequent runs: all mail since last_run date.

Categories: orders, receipts, trips, digests.
"""
import logging
import os
import sys
from datetime import date, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
logger = logging.getLogger('EmailExtractor')

from toolbox.lib.telegram import send_message, escape
from .scanner import (
    get_gmail_service, load_config, load_state, save_state,
    fetch_category_emails,
)
from .categories import orders, receipts, trips, digests, sweep


def run():
    config = load_config()
    state = load_state()

    last_run = state.get('last_run')
    first_run = last_run is None
    today = date.today().strftime('%Y/%m/%d')
    after_date = None if first_run else last_run.replace('-', '/')

    logger.info(f'=== Email Extractor {"(first run)" if first_run else f"(since {last_run})"} ===')

    service = get_gmail_service()

    summaries = {'orders': [], 'receipts': [], 'trips': [], 'digests': [], 'sweep': []}
    errors = 0
    known_digest_senders = config.get('digests', {}).get('known_senders', {})
    raw_digest_senders = config.get('digests', {}).get('raw_senders', {})

    # --- Orders ---
    logger.info('Fetching orders...')
    order_emails = fetch_category_emails(service, 'orders', config,
                                          after_date=after_date, first_run=first_run)
    for email in order_emails:
        try:
            result = orders.process(email, state)
            if result:
                summaries['orders'].append(result)
        except Exception as e:
            logger.error(f'Order processing error ({email["subject"][:50]}): {e}')
            errors += 1

    # --- Receipts ---
    logger.info('Fetching receipts...')
    receipt_emails = fetch_category_emails(service, 'receipts', config,
                                            after_date=after_date, first_run=first_run)
    for email in receipt_emails:
        try:
            result = receipts.process(email, state)
            if result:
                summaries['receipts'].append(result)
        except Exception as e:
            logger.error(f'Receipt processing error ({email["subject"][:50]}): {e}')
            errors += 1

    # --- Trips ---
    logger.info('Fetching trips...')
    trip_emails = fetch_category_emails(service, 'trips', config,
                                         after_date=after_date, first_run=first_run)
    for email in trip_emails:
        try:
            result = trips.process(email, state)
            if result:
                summaries['trips'].append(result)
        except Exception as e:
            logger.error(f'Trip processing error ({email["subject"][:50]}): {e}')
            errors += 1

    # --- Digests ---
    logger.info('Fetching digests...')
    all_digest_senders = {**known_digest_senders, **raw_digest_senders}
    digest_emails = fetch_category_emails(
        service, 'digests',
        {'digests': {'senders': all_digest_senders}},
        after_date=after_date, first_run=first_run,
    )
    for email in digest_emails:
        try:
            result = digests.process(email, known_digest_senders, raw_digest_senders)
            if result:
                summaries['digests'].append(result)
        except Exception as e:
            logger.error(f'Digest processing error ({email["subject"][:50]}): {e}')
            errors += 1

    # --- Weekly sweep ---
    logger.info('Running sweep (weekly)...')
    try:
        result = sweep.run(service, config, state)
        if result:
            summaries['sweep'].append(result)
    except Exception as e:
        logger.error(f'Sweep error: {e}')
        errors += 1

    # Update last_run
    state['last_run'] = date.today().isoformat()
    save_state(state)

    # Build Telegram message
    total = sum(len(v) for v in summaries.values())
    if total == 0 and errors == 0:
        msg = 'Email extractor: nothing new today'
    else:
        lines = [f'<b>Email extractor: {total} items</b>']
        for category, items in summaries.items():
            if not items:
                continue
            lines.append(f'\n<b>{category.capitalize()} ({len(items)}):</b>')
            for s in items:
                lines.append(f'  • {escape(s)}')
        if errors:
            lines.append(f'\nErrors: {errors}')
        msg = '\n'.join(lines)

    logger.info(msg)
    send_message(msg, service='email-extractor')


if __name__ == '__main__':
    run()
