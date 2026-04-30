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

from toolbox.lib.log_manager import LogManager, log
logger = LogManager.get_instance("email-extractor").logger

from toolbox.lib.telegram import send_message, escape, monit_link
from .scanner import (
    get_gmail_service, load_config, load_state, save_state,
    fetch_category_emails,
)
from .categories import orders, receipts, trips, digests, sweep, google_brief, plaud


def run():
    config = load_config()
    state = load_state()

    last_run = state.get('last_run')
    first_run = last_run is None
    today = date.today().strftime('%Y/%m/%d')
    after_date = None if first_run else last_run.replace('-', '/')

    log("RUN_START", "START", "Email extractor run started", data={
        "first_run": first_run,
        "last_run": last_run,
        "after_date": after_date,
    }, app_name="email-extractor")
    logger.info(f'=== Email Extractor {"(first run)" if first_run else f"(since {last_run})"} ===')

    service = get_gmail_service()

    summaries = {'orders': [], 'receipts': [], 'trips': [], 'digests': [], 'google_brief': [], 'sweep': [], 'plaud': []}
    errors = 0
    error_details = []
    known_digest_senders = config.get('digests', {}).get('known_senders', {})
    raw_digest_senders = config.get('digests', {}).get('raw_senders', {})

    # --- Orders ---
    logger.info('Fetching orders...')
    order_emails = fetch_category_emails(service, 'orders', config,
                                          after_date=after_date, first_run=first_run)
    log("CATEGORY_FETCH", "SUCCESS", "Fetched order emails", data={
        "category": "orders",
        "count": len(order_emails),
    }, app_name="email-extractor")
    for email in order_emails:
        try:
            result = orders.process(email, state)
            if result:
                summaries['orders'].append(result)
        except Exception as e:
            logger.error(f'Order processing error ({email["subject"][:50]}): {e}')
            log("CATEGORY_ERROR", "FAILURE", "Order processing error", data={
                "category": "orders",
                "email_id": email.get('id'),
                "subject": email.get('subject', '')[:120],
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="email-extractor")
            errors += 1
            error_details.append(f'orders/{email["subject"][:40]}: {type(e).__name__}')

    # --- Receipts ---
    logger.info('Fetching receipts...')
    receipt_emails = fetch_category_emails(service, 'receipts', config,
                                            after_date=after_date, first_run=first_run)
    log("CATEGORY_FETCH", "SUCCESS", "Fetched receipt emails", data={
        "category": "receipts",
        "count": len(receipt_emails),
    }, app_name="email-extractor")
    for email in receipt_emails:
        try:
            result = receipts.process(email, state)
            if result:
                summaries['receipts'].append(result)
        except Exception as e:
            logger.error(f'Receipt processing error ({email["subject"][:50]}): {e}')
            log("CATEGORY_ERROR", "FAILURE", "Receipt processing error", data={
                "category": "receipts",
                "email_id": email.get('id'),
                "subject": email.get('subject', '')[:120],
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="email-extractor")
            errors += 1
            error_details.append(f'receipts/{email["subject"][:40]}: {type(e).__name__}')

    # --- Trips ---
    logger.info('Fetching trips...')
    trip_emails = fetch_category_emails(service, 'trips', config,
                                         after_date=after_date, first_run=first_run)
    log("CATEGORY_FETCH", "SUCCESS", "Fetched trip emails", data={
        "category": "trips",
        "count": len(trip_emails),
    }, app_name="email-extractor")
    for email in trip_emails:
        try:
            result = trips.process(email, state)
            if result:
                summaries['trips'].append(result)
        except Exception as e:
            logger.error(f'Trip processing error ({email["subject"][:50]}): {e}')
            log("CATEGORY_ERROR", "FAILURE", "Trip processing error", data={
                "category": "trips",
                "email_id": email.get('id'),
                "subject": email.get('subject', '')[:120],
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="email-extractor")
            errors += 1
            error_details.append(f'trips/{email["subject"][:40]}: {type(e).__name__}')

    # --- Digests ---
    logger.info('Fetching digests...')
    all_digest_senders = {**known_digest_senders, **raw_digest_senders}
    digest_emails = fetch_category_emails(
        service, 'digests',
        {'digests': {'senders': all_digest_senders}},
        after_date=after_date, first_run=first_run,
    )
    log("CATEGORY_FETCH", "SUCCESS", "Fetched digest emails", data={
        "category": "digests",
        "count": len(digest_emails),
    }, app_name="email-extractor")
    for email in digest_emails:
        try:
            result = digests.process(email, known_digest_senders, raw_digest_senders)
            if result:
                summaries['digests'].append(result)
        except Exception as e:
            logger.error(f'Digest processing error ({email["subject"][:50]}): {e}')
            log("CATEGORY_ERROR", "FAILURE", "Digest processing error", data={
                "category": "digests",
                "email_id": email.get('id'),
                "subject": email.get('subject', '')[:120],
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="email-extractor")
            errors += 1
            error_details.append(f'digests/{email["subject"][:40]}: {type(e).__name__}')

    # --- Google CC Daily Brief ---
    logger.info('Fetching Google CC brief...')
    brief_emails = fetch_category_emails(service, 'google_brief', config,
                                         after_date=after_date, first_run=first_run)
    log("CATEGORY_FETCH", "SUCCESS", "Fetched Google CC brief emails", data={
        "category": "google_brief",
        "count": len(brief_emails),
    }, app_name="email-extractor")
    for email in brief_emails:
        try:
            result = google_brief.process(email, state)
            if result:
                summaries['google_brief'].append(result)
        except Exception as e:
            logger.error(f'Google brief error ({email["subject"][:50]}): {e}')
            log("CATEGORY_ERROR", "FAILURE", "Google brief processing error", data={
                "category": "google_brief",
                "email_id": email.get('id'),
                "subject": email.get('subject', '')[:120],
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="email-extractor")
            errors += 1
            error_details.append(f'google_brief/{email["subject"][:40]}: {type(e).__name__}')

    # --- Plaud ---
    logger.info('Fetching Plaud emails...')
    plaud_emails = fetch_category_emails(service, 'plaud', config,
                                         after_date=after_date, first_run=first_run)
    log("CATEGORY_FETCH", "SUCCESS", "Fetched Plaud emails", data={
        "category": "plaud",
        "count": len(plaud_emails),
    }, app_name="email-extractor")
    for email in plaud_emails:
        try:
            result = plaud.process(email, state, service=service)
            if result:
                summaries['plaud'].append(result)
        except Exception as e:
            logger.error(f'Plaud processing error ({email["subject"][:50]}): {e}')
            log("CATEGORY_ERROR", "FAILURE", "Plaud processing error", data={
                "category": "plaud",
                "email_id": email.get('id'),
                "subject": email.get('subject', '')[:120],
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="email-extractor")
            errors += 1
            error_details.append(f'plaud/{email["subject"][:40]}: {type(e).__name__}')

    # --- Weekly sweep ---
    logger.info('Running sweep (weekly)...')
    try:
        result = sweep.run(service, config, state)
        log("CATEGORY_FETCH", "SUCCESS", "Completed weekly sweep", data={
            "category": "sweep",
            "count": 1 if result else 0,
        }, app_name="email-extractor")
        if result:
            summaries['sweep'].append(result)
    except Exception as e:
        logger.error(f'Sweep error: {e}')
        log("CATEGORY_ERROR", "FAILURE", "Sweep processing error", data={
            "category": "sweep",
            "error_type": type(e).__name__,
        }, level="ERROR", app_name="email-extractor")
        errors += 1
        error_details.append(f'sweep: {type(e).__name__}')

    # Update last_run
    state['last_run'] = date.today().isoformat()
    save_state(state)

    # Build Telegram message — only send if there's something to report
    total = sum(len(v) for v in summaries.values())
    if total == 0 and errors == 0:
        logger.info('Email extractor: nothing new today')
        log("RUN_COMPLETE", "SUCCESS", "Email extractor run finished with no new items", data={
            "total": 0,
            "errors": 0,
            "counts": {cat: len(items) for cat, items in summaries.items()}
        }, app_name="email-extractor")
        return
    else:
        category_labels = {
            'orders': 'Orders', 'receipts': 'Receipts', 'trips': 'Trips',
            'digests': 'Digests', 'google_brief': 'Google CC', 'sweep': 'Sweep',
            'plaud': 'Plaud',
        }
        lines = [f'<b>Email extractor: {total} items</b>']
        for category, items in summaries.items():
            if not items:
                continue
            label = category_labels.get(category, category.capitalize())
            lines.append(f'\n<b>{label} ({len(items)}):</b>')
            for s in items:
                lines.append(f'  • {escape(s)}')
        if errors:
            lines.append(f'\n<b>{errors} error{"s" if errors > 1 else ""}:</b>')
            for detail in error_details:
                lines.append(f'  • {escape(detail)}')
            lines.append(f'  {monit_link("Check Monit")} · <code>journalctl --user -u email-extractor -n 50</code>')
        msg = '\n'.join(lines)

    log("RUN_COMPLETE", "SUCCESS" if errors == 0 else "WARNING", "Email extractor run finished", data={
        "total": total,
        "errors": errors,
        "counts": {cat: len(items) for cat, items in summaries.items()}
    }, app_name="email-extractor")
    
    logger.info(msg)
    send_message(msg, service='email-extractor · takhan')


if __name__ == '__main__':
    run()
