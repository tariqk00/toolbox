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

LOW_CONFIDENCE_THRESHOLD = 0.7

def _route_result(result, summaries, category, low_confidence_list):
    """Route a processing result to either the main summary or the low-confidence bucket."""
    if not result:
        return
    
    # Handle legacy string-only results (treat as high confidence)
    if isinstance(result, str):
        summaries[category].append(result)
        return

    summary = result.get('summary', '')
    confidence = result.get('confidence', 1.0)
    
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        msg = f"[LOW CONFIDENCE] {summary} (score: {confidence:.2f})"
        summaries[category].append(msg)
        low_confidence_list.append(result)
        logger.warning(f"Low confidence item detected: {summary}")
    else:
        summaries[category].append(summary)


def run():
    config = load_config()
    state = load_state()

    last_run = state.get('last_run')
    first_run = last_run is None
    today = date.today().strftime('%Y/%m/%d')
    after_date = None if first_run else last_run.replace('-', '/')

    logger.info(f'=== Email Extractor {"(first run)" if first_run else f"(since {last_run})"} ===')

    service = get_gmail_service()
    
    # Initialize thread/entity hardening
    state.setdefault('processed_threads', [])
    state.setdefault('processed_entities', [])

    summaries = {'orders': [], 'receipts': [], 'trips': [], 'digests': [], 'google_brief': [], 'sweep': [], 'plaud': []}
    low_confidence = []
    errors = 0
    error_details = []
    known_digest_senders = config.get('digests', {}).get('known_senders', {})
    raw_digest_senders = config.get('digests', {}).get('raw_senders', {})

    # --- Orders ---
    logger.info('Fetching orders...')
    order_emails = fetch_category_emails(service, 'orders', config,
                                          state=state, after_date=after_date, first_run=first_run)
    for email in order_emails:
        try:
            result = orders.process(email, state)
            if result:
                _route_result(result, summaries, 'orders', low_confidence)
                # Mark thread as processed if successful
                if email.get('thread_id'):
                    state['processed_threads'].append(email['thread_id'])
        except Exception as e:
            logger.error(f'Order processing error ({email["subject"][:50]}): {e}')
            errors += 1
            error_details.append(f'orders/{email["subject"][:40]}: {type(e).__name__}')

    # --- Receipts ---
    logger.info('Fetching receipts...')
    receipt_emails = fetch_category_emails(service, 'receipts', config,
                                            state=state, after_date=after_date, first_run=first_run)
    for email in receipt_emails:
        try:
            result = receipts.process(email, state)
            if result:
                _route_result(result, summaries, 'receipts', low_confidence)
                if email.get('thread_id'):
                    state['processed_threads'].append(email['thread_id'])
        except Exception as e:
            logger.error(f'Receipt processing error ({email["subject"][:50]}): {e}')
            errors += 1
            error_details.append(f'receipts/{email["subject"][:40]}: {type(e).__name__}')

    # --- Trips ---
    logger.info('Fetching trips...')
    trip_emails = fetch_category_emails(service, 'trips', config,
                                         state=state, after_date=after_date, first_run=first_run)
    for email in trip_emails:
        try:
            result = trips.process(email, state)
            if result:
                _route_result(result, summaries, 'trips', low_confidence)
                if email.get('thread_id'):
                    state['processed_threads'].append(email['thread_id'])
        except Exception as e:
            logger.error(f'Trip processing error ({email["subject"][:50]}): {e}')
            errors += 1
            error_details.append(f'trips/{email["subject"][:40]}: {type(e).__name__}')

    # --- Digests ---
    logger.info('Fetching digests...')
    all_digest_senders = {**known_digest_senders, **raw_digest_senders}
    digest_emails = fetch_category_emails(
        service, 'digests',
        {'digests': {'senders': all_digest_senders}},
        state=state, after_date=after_date, first_run=first_run,
    )
    for email in digest_emails:
        try:
            result = digests.process(email, known_digest_senders, raw_digest_senders)
            if result:
                _route_result(result, summaries, 'digests', low_confidence)
                if email.get('thread_id'):
                    state['processed_threads'].append(email['thread_id'])
        except Exception as e:
            logger.error(f'Digest processing error ({email["subject"][:50]}): {e}')
            errors += 1
            error_details.append(f'digests/{email["subject"][:40]}: {type(e).__name__}')

    # --- Google CC Daily Brief ---
    logger.info('Fetching Google CC brief...')
    brief_emails = fetch_category_emails(service, 'google_brief', config,
                                         state=state, after_date=after_date, first_run=first_run)
    for email in brief_emails:
        try:
            result = google_brief.process(email, state)
            if result:
                _route_result(result, summaries, 'google_brief', low_confidence)
                if email.get('thread_id'):
                    state['processed_threads'].append(email['thread_id'])
        except Exception as e:
            logger.error(f'Google brief error ({email["subject"][:50]}): {e}')
            errors += 1
            error_details.append(f'google_brief/{email["subject"][:40]}: {type(e).__name__}')

    # --- Plaud ---
    logger.info('Fetching Plaud emails...')
    plaud_emails = fetch_category_emails(service, 'plaud', config,
                                         state=state, after_date=after_date, first_run=first_run)
    for email in plaud_emails:
        try:
            result = plaud.process(email, state, service=service)
            if result:
                _route_result(result, summaries, 'plaud', low_confidence)
                if email.get('thread_id'):
                    state['processed_threads'].append(email['thread_id'])
        except Exception as e:
            logger.error(f'Plaud processing error ({email["subject"][:50]}): {e}')
            errors += 1
            error_details.append(f'plaud/{email["subject"][:40]}: {type(e).__name__}')

    # --- Weekly sweep ---
    logger.info('Running sweep (weekly)...')
    try:
        result = sweep.run(service, config, state)
        if result:
            _route_result(result, summaries, 'sweep', low_confidence)
    except Exception as e:
        logger.error(f'Sweep error: {e}')
        errors += 1
        error_details.append(f'sweep: {type(e).__name__}')

    # Update last_run and harden state
    state['last_run'] = date.today().isoformat()
    # Deduplicate and limit thread history to last 500
    state['processed_threads'] = list(set(state.get('processed_threads', [])))[-500:]
    # Deduplicate and limit entity history to last 1000
    state['processed_entities'] = list(set(state.get('processed_entities', [])))[-1000:]
    save_state(state)

    # Build Telegram message — only send if there's something to report
    total = sum(len(v) for v in summaries.values())
    if total == 0 and errors == 0:
        logger.info('Email extractor: nothing new today')
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
        
        if low_confidence:
            lines.append(f'\n⚠️ <b>Low Confidence ({len(low_confidence)})</b>')
            lines.append('Items moved to low-confidence bucket for manual review.')

        if errors:
            lines.append(f'\n<b>{errors} error{"s" if errors > 1 else ""}:</b>')
            for detail in error_details:
                lines.append(f'  • {escape(detail)}')
            lines.append(f'  {monit_link("Check Monit")} · <code>journalctl --user -u email-extractor -n 50</code>')
        msg = '\n'.join(lines)

    log("RUN_COMPLETE", "SUCCESS" if errors == 0 else "WARNING", "Email extractor run finished", data={
        "total": total,
        "errors": errors,
        "counts": {cat: len(items) for cat, items in summaries.items()},
        "low_confidence_count": len(low_confidence)
    }, app_name="email-extractor")
    
    logger.info(msg)
    send_message(msg, service='email-extractor · takhan')


if __name__ == '__main__':
    run()
