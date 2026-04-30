"""
Trips category processor.
First email: full itinerary block with LLM-extracted details (Groq).
Return leg: appended to existing block in-place, header updated → to ↔.
Status updates: update **Status:** line in-place.
Header date = travel date (departure/check-in), not email date.
"""
import re
import logging
from ..writers import append_to_memory, update_in_memory, get_memory_content, block_exists
from ..enrichment import enrich_trip
from ..scanner import html_to_text
from toolbox.lib.entity_ids import render_entity_comment, travel_entity_id

logger = logging.getLogger('EmailExtractor.Trips')


# ── LLM prompts ──────────────────────────────────────────────────────────────

FLIGHT_PROMPT = """\
Extract flight details from this {vendor} email.
Return ONLY valid JSON:
{{
  "origin": "JFK",
  "destination": "ATL",
  "flight_number": "DL 1234",
  "departure_date": "YYYY-MM-DD",
  "departure_time": "HH:MM",
  "arrival_time": "HH:MM",
  "seat": "",
  "is_return": false
}}
Rules:
- departure_date: YYYY-MM-DD, or "" if not found
- departure_time / arrival_time: 24h HH:MM, or "" if not found
- seat: seat assignment if present, or ""
- is_return: true if this is the return/homebound leg
- Use "" for missing string fields, false for missing booleans

Subject: {subject}
Body:
{body}"""

HOTEL_PROMPT = """\
Extract hotel reservation details from this {vendor} email.
Return ONLY valid JSON:
{{
  "destination": "city or property name",
  "checkin_date": "YYYY-MM-DD",
  "checkout_date": "YYYY-MM-DD",
  "nights": 0,
  "room_type": ""
}}
Rules:
- dates: YYYY-MM-DD, or "" if not found
- nights: integer count, or 0 if not found
- room_type: room category/description, or ""

Subject: {subject}
Body:
{body}"""

CAR_PROMPT = """\
Extract car rental details from this {vendor} email.
Return ONLY valid JSON:
{{
  "pickup_location": "airport or city",
  "pickup_date": "YYYY-MM-DD",
  "pickup_time": "HH:MM",
  "return_date": "YYYY-MM-DD",
  "return_time": "HH:MM",
  "car_class": ""
}}
Rules:
- dates: YYYY-MM-DD, or "" if not found
- times: 24h HH:MM, or "" if not found
- car_class: vehicle category, or ""

Subject: {subject}
Body:
{body}"""

DINING_PROMPT = """\
Extract dining reservation details from this {vendor} email.
Return ONLY valid JSON:
{{
  "restaurant": "restaurant name",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "party_size": 0
}}
Rules:
- date: YYYY-MM-DD, or "" if not found
- time: 24h HH:MM, or "" if not found
- party_size: integer, or 0 if not found

Subject: {subject}
Body:
{body}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prep_body(plain: str, html: str) -> str:
    if plain and not re.search(r'<[a-zA-Z]+[\s>]', plain[:500]):
        return plain
    if html:
        text, _ = html_to_text(html)
        return text
    return plain


def _extract_confirmation(subject: str, plain: str) -> str:
    for pattern in [
        r'[Cc]onfirmation\s*[Nn]umber[:\s]+([A-Z0-9]{4,12})',
        r'[Cc]onfirmation[:\s#]+([A-Z0-9]{4,12})',
        r'\b([A-Z]{2,6}\d{3,8})\b',
        r'[Rr]eservation\s*(?:ID|#)[:\s]+([A-Z0-9\-]{4,20})',
    ]:
        for text in (subject, plain[:2000]):
            m = re.search(pattern, text)
            if m:
                val = m.group(1)
                if len(val) >= 4 and not val.isdigit():
                    return val
    m = re.search(r'[Cc]onfirmation[:\s#]+(\d{6,})', plain[:2000])
    return m.group(1) if m else ''


def _extract_trip_type(vendor: str, subject: str) -> str:
    lower = subject.lower()
    if vendor in ('Delta', 'United', 'American Airlines', 'Southwest', 'JetBlue',
                  'Alaska Airlines', 'Spirit', 'Frontier', 'AmEx Global Business Travel'):
        return 'Flight'
    if vendor in ('National Car Rental', 'Enterprise', 'Hertz', 'Avis', 'Budget', 'Alamo'):
        return 'Car Rental'
    if vendor in ('Resy', 'OpenTable'):
        return 'Dining'
    if vendor in ('Marriott Vacation Club', 'Marriott', 'Hilton', 'Hyatt', 'IHG',
                  'Airbnb', 'Vrbo', 'Hotels.com', 'Booking.com', 'Expedia'):
        return 'Hotel'
    if vendor == 'Amtrak':
        return 'Train'
    if any(w in lower for w in ('flight', 'check in', 'boarding', 'airline', 'departs', 'e-ticket')):
        return 'Flight'
    if any(w in lower for w in ('hotel', 'resort', 'check-in', 'check in', 'inn', 'suite')):
        return 'Hotel'
    if 'car rental' in lower or 'car reservation' in lower:
        return 'Car Rental'
    if 'restaurant' in lower or 'dining' in lower or 'reservation at' in lower:
        return 'Dining'
    if 'train' in lower or 'amtrak' in lower:
        return 'Train'
    return 'Travel'


def _extract_destination(vendor: str, subject: str, plain: str) -> str:
    if vendor == 'Marriott Vacation Club':
        m = re.search(r'Maui|Kauai|Hawaii|Honolulu|Waikiki', subject + ' ' + plain[:1000], re.IGNORECASE)
        if m:
            return m.group(0)
    if vendor == 'Delta':
        m = re.search(r'flight\s+(?:to\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', subject, re.IGNORECASE)
        if m:
            return m.group(1)
    if vendor == 'National Car Rental':
        m = re.search(r'at\s+([A-Z\s]+(?:ARPT|AIRPORT))', subject)
        if m:
            return m.group(1).strip()
    if vendor == 'Resy':
        m = re.search(r'at\s+([A-Z][A-Z\s&]+)', subject)
        if m:
            return m.group(1).title().strip()
    return ''


def _extract_status(subject: str) -> str | None:
    lower = subject.lower()
    if 'cancel' in lower:
        return 'Cancelled'
    if any(w in lower for w in ('confirmed', 'confirmation', 'booked', 'reservation')):
        return 'Confirmed'
    if 'check in' in lower or 'check-in' in lower or 'time to check in' in lower:
        return 'Check-in'
    if any(w in lower for w in ('days until', 'upcoming arrival', 'arrival reminder')):
        return 'Reminder'
    if any(w in lower for w in ('change', 'update', 'modified')):
        return 'Changed'
    return None


def _trip_url(vendor: str, confirmation: str) -> str:
    if not confirmation:
        return ''
    if vendor in ('Delta', 'AmEx Global Business Travel'):
        return f'https://www.delta.com/us/en/my-trips/reservation-details?confirmationNumber={confirmation}'
    if vendor == 'Marriott Vacation Club':
        return f'https://www.marriott.com/reservation/retrieveReservation.mi?confirmationNumber={confirmation}'
    if vendor == 'National Car Rental':
        return f'https://www.nationalcar.com/en_US/car-rental/reservation/deeplink/retrieve.html?resNumber={confirmation}'
    return ''


def _extract_trip_details_llm(trip_type: str, vendor: str, subject: str, body: str) -> dict:
    """Use Groq to extract type-specific itinerary details."""
    from toolbox.lib.llm import call_json
    prompts = {
        'Flight': FLIGHT_PROMPT,
        'Hotel': HOTEL_PROMPT,
        'Car Rental': CAR_PROMPT,
        'Dining': DINING_PROMPT,
    }
    template = prompts.get(trip_type)
    if not template:
        return {}
    prompt = template.format(vendor=vendor, subject=subject, body=body[:4000])
    return call_json(prompt, max_tokens=300)


def _build_return_section(details: dict) -> str:
    """Build the ### Return block for a flight's return leg."""
    lines = ['### Return']
    if details.get('flight_number'):
        lines.append(f'**Flight:** {details["flight_number"]}')
    dep_date = details.get('departure_date', '')
    dep_time = details.get('departure_time', '')
    origin = details.get('origin', '')
    dest = details.get('destination', '')
    dep_str = f'{dep_date} {dep_time}'.strip() if (dep_date or dep_time) else dep_date
    if origin:
        dep_str += f' — {origin}' if dep_str else origin
    if dep_str:
        lines.append(f'**Departure:** {dep_str}')
    arr_time = details.get('arrival_time', '')
    arr_str = arr_time
    if dest:
        arr_str = f'{arr_str} — {dest}' if arr_str else dest
    if arr_str:
        lines.append(f'**Arrival:** {arr_str}')
    if details.get('seat'):
        lines.append(f'**Seat:** {details["seat"]}')
    return '\n'.join(lines)


def _build_block(trip_type: str, email_date: str, vendor: str, confirmation: str,
                 status_line: str, details: dict, destination: str) -> tuple[str, str, str]:
    """
    Build a full itinerary block.
    Returns (block_text, travel_date, label).
    travel_date: the actual trip date (departure/check-in) for the block header.
    label: short description for Telegram summary (route, destination, restaurant).
    """
    if trip_type == 'Flight':
        origin = details.get('origin', '')
        dest = details.get('destination', '') or destination
        route = f'{origin} → {dest}' if origin and dest else (dest or origin or '')
        travel_date = details.get('departure_date', '') or email_date
        label = route or dest or vendor

        lines = [f'## {travel_date} — Flight{f" — {route}" if route else ""}']
        lines.append(render_entity_comment(travel_entity_id(vendor, trip_type, confirmation, travel_date, label)))
        lines.append(f'**Vendor:** {vendor}')
        if confirmation:
            lines.append(f'**Confirmation:** {confirmation}')
            url = _trip_url(vendor, confirmation)
            if url:
                lines.append(f'**URL:** {url}')
        lines.append(status_line)
        lines.append('')
        lines.append('### Outbound')
        if details.get('flight_number'):
            lines.append(f'**Flight:** {details["flight_number"]}')
        dep_time = details.get('departure_time', '')
        dep_str = f'{travel_date} {dep_time}'.strip() if dep_time else travel_date
        if origin:
            dep_str += f' — {origin}'
        lines.append(f'**Departure:** {dep_str}')
        arr_time = details.get('arrival_time', '')
        if arr_time and dest:
            lines.append(f'**Arrival:** {arr_time} — {dest}')
        elif arr_time:
            lines.append(f'**Arrival:** {arr_time}')
        if details.get('seat'):
            lines.append(f'**Seat:** {details["seat"]}')

    elif trip_type == 'Hotel':
        dest = details.get('destination', '') or destination
        checkin = details.get('checkin_date', '') or email_date
        checkout = details.get('checkout_date', '')
        nights = details.get('nights', 0)
        room = details.get('room_type', '')
        travel_date = checkin
        label = dest or vendor

        lines = [f'## {travel_date} — Hotel{f" — {dest}" if dest else ""}']
        lines.append(render_entity_comment(travel_entity_id(vendor, trip_type, confirmation, travel_date, label)))
        lines.append(f'**Vendor:** {vendor}')
        if confirmation:
            lines.append(f'**Confirmation:** {confirmation}')
            url = _trip_url(vendor, confirmation)
            if url:
                lines.append(f'**URL:** {url}')
        lines.append(status_line)
        lines.append('')
        lines.append(f'**Check-in:** {checkin}')
        if checkout:
            lines.append(f'**Check-out:** {checkout}')
        if nights:
            lines.append(f'**Nights:** {nights}')
        if room:
            lines.append(f'**Room:** {room}')

    elif trip_type == 'Car Rental':
        loc = details.get('pickup_location', '') or destination
        pickup_date = details.get('pickup_date', '') or email_date
        pickup_time = details.get('pickup_time', '')
        return_date = details.get('return_date', '')
        return_time = details.get('return_time', '')
        car_class = details.get('car_class', '')
        travel_date = pickup_date
        label = loc or vendor

        lines = [f'## {travel_date} — Car Rental{f" — {loc}" if loc else ""}']
        lines.append(render_entity_comment(travel_entity_id(vendor, trip_type, confirmation, travel_date, label)))
        lines.append(f'**Vendor:** {vendor}')
        if confirmation:
            lines.append(f'**Confirmation:** {confirmation}')
            url = _trip_url(vendor, confirmation)
            if url:
                lines.append(f'**URL:** {url}')
        lines.append(status_line)
        lines.append('')
        pickup_str = f'{pickup_date} {pickup_time}'.strip() if pickup_time else pickup_date
        if loc:
            pickup_str += f' — {loc}'
        lines.append(f'**Pickup:** {pickup_str}')
        if return_date:
            return_str = f'{return_date} {return_time}'.strip() if return_time else return_date
            lines.append(f'**Return:** {return_str}')
        if car_class:
            lines.append(f'**Car class:** {car_class}')

    elif trip_type == 'Dining':
        restaurant = details.get('restaurant', '') or destination
        res_date = details.get('date', '') or email_date
        res_time = details.get('time', '')
        party = details.get('party_size', 0)
        travel_date = res_date
        label = restaurant or vendor

        lines = [f'## {travel_date} — Dining{f" — {restaurant}" if restaurant else ""}']
        lines.append(render_entity_comment(travel_entity_id(vendor, trip_type, confirmation, travel_date, label)))
        lines.append(f'**Vendor:** {vendor}')
        if confirmation:
            lines.append(f'**Confirmation:** {confirmation}')
            url = _trip_url(vendor, confirmation)
            if url:
                lines.append(f'**URL:** {url}')
        lines.append(status_line)
        lines.append('')
        date_str = f'{res_date} at {res_time}' if res_time else res_date
        lines.append(f'**Date:** {date_str}')
        if party:
            lines.append(f'**Party:** {party}')

    else:
        travel_date = email_date
        label = destination or vendor
        lines = [f'## {travel_date} — {trip_type}{f" — {destination}" if destination else ""}']
        lines.append(render_entity_comment(travel_entity_id(vendor, trip_type, confirmation, travel_date, label)))
        lines.append(f'**Vendor:** {vendor}')
        if confirmation:
            lines.append(f'**Confirmation:** {confirmation}')
            url = _trip_url(vendor, confirmation)
            if url:
                lines.append(f'**URL:** {url}')
        lines.append(status_line)

    lines.append('---')
    return '\n'.join(lines), travel_date, label


# ── Main processor ────────────────────────────────────────────────────────────

def process(email: dict, state: dict) -> str | None:
    vendor = email['vendor']
    subject = email['subject']
    plain = email.get('plain') or ''
    html = email.get('html') or ''
    date = email['date']

    status = _extract_status(subject)
    if not status:
        return None

    trip_type = _extract_trip_type(vendor, subject)
    confirmation = _extract_confirmation(subject, plain)
    destination = _extract_destination(vendor, subject, plain)
    filename = 'Travel.md'

    known_trips = state.setdefault('trip_confirmations', {})
    state_key = confirmation if confirmation else f'{vendor}:{trip_type}:{date[:7]}'

    # ── Known trip ────────────────────────────────────────────────────────────
    if state_key in known_trips:
        prev = known_trips[state_key]
        prev_status = prev.get('status', '')

        # Return leg detection: same confirmation, flight, Confirmed, no return yet
        if (trip_type == 'Flight' and status == 'Confirmed'
                and status == prev_status and not prev.get('has_return')):
            body = _prep_body(plain, html)
            details = _extract_trip_details_llm(trip_type, vendor, subject, body)
            if details.get('is_return') is True:
                return_section = _build_return_section(details)
                old_block = prev.get('block', '')
                if old_block:
                    new_block = old_block.replace(' → ', ' ↔ ', 1)
                    new_block = new_block.rstrip()
                    if new_block.endswith('---'):
                        new_block = new_block[:-3].rstrip() + '\n\n' + return_section + '\n---'
                    else:
                        new_block += '\n\n' + return_section + '\n---'
                    if update_in_memory(None, filename, old_block, new_block):
                        prev['block'] = new_block
                    prev['has_return'] = True
                else:
                    append_to_memory(None, filename, return_section)
                    prev['has_return'] = True

                ret_origin = details.get('origin', '')
                ret_dest = details.get('destination', '')
                ret_route = f'{ret_origin} → {ret_dest}' if ret_origin and ret_dest else ''
                summary = f'Flight: {vendor} — return leg added'
                if ret_route:
                    summary += f' ({ret_route})'
                if confirmation:
                    summary += f' [{confirmation}]'
                url = _trip_url(vendor, confirmation)
                if url:
                    summary += f'\n{url}'
                logger.info(f'Travel.md: return leg — {vendor} {confirmation}')
                return summary

        if status == prev_status:
            return None

        # Status update — replace **Status:** line in-place
        old_line = prev.get('status_line', f'**Status:** [{prev_status}] {prev["date"]}')
        new_line = f'**Status:** [{status}] {date}'
        update_in_memory(None, filename, old_line, new_line)
        if prev.get('block'):
            prev['block'] = prev['block'].replace(old_line, new_line, 1)
        prev['status'] = status
        prev['status_line'] = new_line
        prev['date'] = date

        label = prev.get('label', f'{trip_type} ({vendor})')
        summary = f'{label} ({vendor}) → {status} [{date}]'
        url = _trip_url(vendor, confirmation)
        if url:
            summary += f'\n{url}'
        logger.info(f'Travel.md: status update — {vendor} {confirmation or state_key} → {status}')
        return summary

    # ── Content-based safety net ──────────────────────────────────────────────
    existing_content = get_memory_content(None, filename)
    if confirmation and confirmation in existing_content:
        logger.debug(f'Travel.md: skipping duplicate (confirmation {confirmation} already in file)')
        status_line = f'**Status:** [{status}] {date}'
        known_trips[state_key] = {
            'vendor': vendor, 'status': status, 'status_line': status_line,
            'date': date, 'destination': destination, 'trip_type': trip_type,
            'label': destination or vendor, 'has_return': False, 'block': '',
            'entity_id': travel_entity_id(vendor, trip_type, confirmation, date, destination or vendor),
        }
        return None
    elif not confirmation:
        dedup_ids = (vendor, trip_type)
        if block_exists(existing_content, date, *dedup_ids):
            logger.debug(f'Travel.md: skipping duplicate ({state_key})')
            status_line = f'**Status:** [{status}] {date}'
            known_trips[state_key] = {
                'vendor': vendor, 'status': status, 'status_line': status_line,
                'date': date, 'destination': destination, 'trip_type': trip_type,
                'label': destination or vendor, 'has_return': False, 'block': '',
                'entity_id': travel_entity_id(vendor, trip_type, confirmation, date, destination or vendor),
            }
            return None

    # ── New trip — full itinerary block ───────────────────────────────────────
    body = _prep_body(plain, html)
    details = _extract_trip_details_llm(trip_type, vendor, subject, body)

    status_line = f'**Status:** [{status}] {date}'
    block, travel_date, label = _build_block(
        trip_type, date, vendor, confirmation, status_line, details, destination
    )

    append_to_memory(None, filename, block)

    known_trips[state_key] = {
        'vendor': vendor, 'status': status, 'status_line': status_line,
        'date': date, 'travel_date': travel_date, 'destination': destination,
        'trip_type': trip_type, 'label': label,
        'has_return': False,
        'block': block,
        'entity_id': travel_entity_id(vendor, trip_type, confirmation, travel_date, label),
    }

    summary = f'{trip_type}: {label} ({vendor}) [{status}]'
    if travel_date and travel_date != date:
        summary += f' — {travel_date}'
    url = _trip_url(vendor, confirmation)
    if url:
        summary += f'\n{url}'
    summary = enrich_trip(summary, trip_type, vendor, label, status, travel_date)
    logger.info(f'Travel.md: new {trip_type} — {label} ({vendor}) [{status}]')
    return summary
