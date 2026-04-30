import importlib

from toolbox.lib.task_utils import (
    create_unique_tasks,
    dedupe_action_items,
    normalize_task_title,
)


class _Request:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class _Tasks:
    def __init__(self, existing):
        self.existing = existing

    def list(self, **kwargs):
        return _Request({"items": [{"title": title} for title in self.existing]})


class _Service:
    def __init__(self, existing=()):
        self._tasks = _Tasks(existing)

    def tasks(self):
        return self._tasks


def test_normalize_task_title_strips_effort_prefix():
    assert normalize_task_title("(15 min)  Follow up with client ") == "follow up with client"


def test_create_unique_tasks_skips_existing_and_same_batch_duplicates(monkeypatch):
    created = []
    tasks_mod = importlib.import_module("toolbox.lib.tasks")

    def fake_create_task(service, list_id, title, due=None, notes=None):
        created.append((list_id, title, due, notes))

    monkeypatch.setattr(tasks_mod, "create_task", fake_create_task)

    service = _Service(existing=["(5 min) Pay invoice"])
    count = create_unique_tasks(
        service,
        "tasks-list",
        [
            {"text": "Pay invoice"},
            {"text": "Book flight", "due": "2026-05-01"},
            {"text": "Book flight", "due": "2026-05-01"},
        ],
        title_fn=lambda item: item["text"],
        due_fn=lambda item: item.get("due"),
        notes_fn=lambda item: "source note",
    )

    assert count == 1
    assert created == [("tasks-list", "Book flight", "2026-05-01", "source note")]


def test_dedupe_action_items_uses_subject_and_sender():
    items = [
        {"subject": "Pay invoice", "sender": "billing@example.com", "reason": "first"},
        {"subject": " pay   invoice ", "sender": "billing@example.com", "reason": "duplicate"},
        {"subject": "Pay invoice", "sender": "ops@example.com", "reason": "different sender"},
    ]

    assert dedupe_action_items(items) == [items[0], items[2]]
