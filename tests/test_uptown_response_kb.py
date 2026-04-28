import unittest
from unittest.mock import patch

from toolbox.services.inbox_scanner import uptown_response_kb as kb


def _message(
    msg_id: str,
    thread_id: str,
    from_header: str,
    subject: str,
    body: str,
    date_header: str,
    label_ids=None,
    cc: str = '',
    to: str = 'operations@uptownedenton.com',
):
    payload_headers = [
        {'name': 'From', 'value': from_header},
        {'name': 'Subject', 'value': subject},
        {'name': 'Date', 'value': date_header},
        {'name': 'To', 'value': to},
    ]
    if cc:
        payload_headers.append({'name': 'Cc', 'value': cc})
    return {
        'id': msg_id,
        'threadId': thread_id,
        'labelIds': label_ids or [],
        'payload': {
            'headers': payload_headers,
            'mimeType': 'text/plain',
            'body': {'data': body.encode('utf-8').hex()},
        },
    }


def _b64_message(*args, **kwargs):
    import base64

    msg = _message(*args, **kwargs)
    body = args[4].encode('utf-8')
    msg['payload']['body']['data'] = base64.urlsafe_b64encode(body).decode().rstrip('=')
    return msg


class TestBuildKbEntry(unittest.TestCase):
    def test_direct_reply_ingested(self):
        thread = {
            'id': 'thread-1',
            'messages': [
                _b64_message(
                    'm1', 'thread-1', 'Jane Prospect <jane@example.com>',
                    '2BR availability question',
                    'Hi, I am Jane Prospect and wanted to ask about two bedroom availability and pet policy.',
                    'Mon, 28 Apr 2026 09:00:00 -0400',
                ),
                _b64_message(
                    'm2', 'thread-1', 'Christina Manzella <operations@uptownedenton.com>',
                    'Re: 2BR availability question',
                    'Hi Jane,\n\nThanks for reaching out. We would love to schedule a tour and go over pricing, pet policy, and next steps on a quick call.\n\nChristina | Uptown Edenton',
                    'Mon, 28 Apr 2026 10:00:00 -0400',
                    label_ids=['SENT'],
                ),
            ],
        }

        entry = kb.build_kb_entry(thread)
        self.assertIsNotNone(entry)
        self.assertEqual(entry['lead_name'], 'Jane Prospect')
        self.assertEqual(entry['source'], 'Direct')
        self.assertEqual(len(entry['responses']), 1)

    def test_forwarded_response_ingested(self):
        thread = {
            'id': 'thread-2',
            'messages': [
                _b64_message(
                    'm1', 'thread-2', 'Rental Client Services <rentalclientservices@zillowrentals.com>',
                    'New lead from Zillow',
                    'Prospect asking for pricing and a tour for a one bedroom apartment.',
                    'Mon, 28 Apr 2026 09:00:00 -0400',
                ),
                _b64_message(
                    'm2', 'thread-2', 'Christina Manzella <christina@example.com>',
                    'Fwd: New lead from Zillow',
                    'Happy to help. We can review pricing, availability, and set up a tour this week.\n\nForwarded for visibility.',
                    'Mon, 28 Apr 2026 10:00:00 -0400',
                    label_ids=['SENT'],
                    cc='takhan@gmail.com',
                ),
            ],
        }

        entry = kb.build_kb_entry(thread)
        self.assertIsNotNone(entry)
        self.assertEqual(entry['source'], 'Zillow')
        self.assertTrue(entry['responses'][0]['forwarded'])

    def test_non_substantive_followup_excluded(self):
        thread = {
            'id': 'thread-3',
            'messages': [
                _b64_message(
                    'm1', 'thread-3', 'Lead Person <lead@example.com>',
                    'Tour question',
                    'Can I schedule a tour and ask about the application process?',
                    'Mon, 28 Apr 2026 09:00:00 -0400',
                ),
                _b64_message(
                    'm2', 'thread-3', 'Christina Manzella <operations@uptownedenton.com>',
                    'Re: Tour question',
                    'Thanks, what time works for you?',
                    'Mon, 28 Apr 2026 10:00:00 -0400',
                    label_ids=['SENT'],
                ),
            ],
        }

        self.assertIsNone(kb.build_kb_entry(thread))

    def test_non_lead_chamber_thread_excluded(self):
        thread = {
            'id': 'thread-4',
            'messages': [
                _b64_message(
                    'm1', 'thread-4', 'Susan Creed <susan@example.com>',
                    'Pics for banquet',
                    'Hi Christina - could you send me a few pictures for our banquet slideshow please?',
                    'Tue, 08 Apr 2026 09:00:00 -0400',
                ),
                _b64_message(
                    'm2', 'thread-4', 'Christina Manzella <operations@uptownedenton.com>',
                    'Fwd: Pics for banquet',
                    'Hi Susan,\n\nYes no problem ill get you a few slides by the end of the week.\n\nChristina',
                    'Tue, 08 Apr 2026 10:00:00 -0400',
                    label_ids=['SENT'],
                ),
            ],
        }

        self.assertIsNone(kb.build_kb_entry(thread))

    def test_outbound_only_template_thread_excluded(self):
        thread = {
            'id': 'thread-5',
            'messages': [
                _b64_message(
                    'm1', 'thread-5', 'Christina Manzella <operations@uptownedenton.com>',
                    'Uptown Edenton Inquiry',
                    'Hi Tracey,\n\nThank you for your interest in a unit at the Uptown Edenton. Units start at $1000 and we would love to schedule a tour.\n\nChristina',
                    'Thu, 03 Apr 2026 10:00:00 -0400',
                    label_ids=['SENT'],
                ),
            ],
        }

        self.assertIsNone(kb.build_kb_entry(thread))

    def test_quoted_previous_message_removed_from_inquiry(self):
        thread = {
            'id': 'thread-6',
            'messages': [
                _b64_message(
                    'm1', 'thread-6', 'Matthew Rubio <matt@example.com>',
                    'Availability at the Uptown Edenton',
                    'Good afternoon are these apartments still available? Please email or contact me at 305-807-1180 to move forward if they are available.\n\nOn Mon, Mar 2, 2026 at 2:06 PM Christina Manzella <operations@uptownedenton.com> wrote:',
                    'Sun, 06 Apr 2026 09:00:00 -0400',
                ),
                _b64_message(
                    'm2', 'thread-6', 'Christina Manzella <operations@uptownedenton.com>',
                    'Re: Availability at the Uptown Edenton',
                    'Hi Matt,\n\nThe next available room will be ready on Saturday 4/25. We can review lease options and next steps by phone.\n\nChristina',
                    'Sun, 06 Apr 2026 10:00:00 -0400',
                    label_ids=['SENT'],
                ),
            ],
        }

        entry = kb.build_kb_entry(thread)
        self.assertIsNotNone(entry)
        self.assertNotIn('Christina Manzella <operations@uptownedenton.com> wrote', entry['inquiry_text'])

    def test_quoted_only_inbound_message_is_skipped(self):
        thread = {
            'id': 'thread-7',
            'messages': [
                _b64_message(
                    'm1', 'thread-7', 'Brayn Shultis <brayn@example.com>',
                    'Lease for Uptown Edenton',
                    'On Wed, Apr 22, 2026, 3:44 PM Christina Manzella <operations@uptownedenton.com> wrote:',
                    'Wed, 22 Apr 2026 16:00:00 -0400',
                ),
                _b64_message(
                    'm2', 'thread-7', 'Christina Manzella <operations@uptownedenton.com>',
                    'Re: Lease for Uptown Edenton',
                    'Hi Bryan,\n\nHere is your lease if you could sign pages 3 and 8 that would be great.\n\nChristina',
                    'Wed, 22 Apr 2026 16:10:00 -0400',
                    label_ids=['SENT'],
                ),
            ],
        }

        self.assertIsNone(kb.build_kb_entry(thread))


class TestFilenameAndPromptSelection(unittest.TestCase):
    def test_existing_thread_filename_reused(self):
        entry = {
            'date': '2026-04-28',
            'lead_name': 'Jane Prospect',
            'subject': 'Availability',
            'thread_id': 'thread-9',
        }
        filename = kb.kb_filename(entry, ['2026-04-10 -- Old-Lead -- old-subject -- thread-9.md'])
        self.assertEqual(filename, '2026-04-10 -- Old-Lead -- old-subject -- thread-9.md')

    @patch('toolbox.services.inbox_scanner.uptown_response_kb.load_kb_entries')
    def test_relevant_examples_selected_for_prompt(self, mock_load):
        mock_load.return_value = [
            {
                'source': 'Zillow',
                'subject': 'Pricing and tour',
                'inquiry_text': 'Looking for pricing and a tour for a one bedroom apartment.',
                'responses': [{'body': 'We would love to schedule a tour and review pricing on a call.'}],
            },
            {
                'source': 'Direct',
                'subject': 'Maintenance vendor question',
                'inquiry_text': 'Vendor asking about an invoice.',
                'responses': [{'body': 'Please send the invoice to accounting.'}],
            },
        ]

        prompt_examples = kb.build_prompt_examples({
            'platform': 'Zillow',
            'subject': 'Need pricing for one bedroom',
            'unit_interest': 'one bedroom',
            'questions': ['Can I tour this week?', 'What is pricing like?'],
            'body': 'Interested in pricing and a tour for a one bedroom.',
        })

        self.assertIn('Example 1 — Zillow lead', prompt_examples)
        self.assertIn('schedule a tour', prompt_examples)
        self.assertNotIn('invoice', prompt_examples)


if __name__ == '__main__':
    unittest.main()
