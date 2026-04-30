from toolbox.lib.entity_ids import (
    calendar_entity_id,
    order_entity_id,
    plaud_entity_id,
    render_entity_comment,
    task_entity_id,
    travel_entity_id,
)


def test_entity_ids_are_deterministic():
    assert order_entity_id("Amazon", "112-3456789") == order_entity_id("Amazon", "112-3456789")
    assert travel_entity_id("Delta", "Flight", "HXXKJD", "2026-04-15", "JFK → ATL") == travel_entity_id(
        "Delta", "Flight", "HXXKJD", "2026-04-15", "JFK → ATL"
    )
    assert plaud_entity_id("Project Sync", "2026-04-26") == plaud_entity_id("Project Sync", "2026-04-26")


def test_entity_ids_change_with_domain_specific_keys():
    assert order_entity_id("Amazon", "112-3456789") != order_entity_id("Amazon", "112-0000000")
    assert task_entity_id("plaud:sync", "Follow up", "2026-04-30") != task_entity_id(
        "google_brief", "Follow up", "2026-04-30"
    )
    assert calendar_entity_id("google_brief", "Dinner", "Fri Apr 17 6:00 PM", "Maui") != calendar_entity_id(
        "google_brief", "Dinner", "Fri Apr 17 8:00 PM", "Maui"
    )


def test_render_entity_comment_is_hidden_marker():
    entity_id = order_entity_id("Amazon", "112-3456789")
    assert render_entity_comment(entity_id) == f"<!-- entity_id: {entity_id} -->"


def test_plaud_markdown_includes_entity_id_marker():
    from toolbox.services.email_extractor.categories import plaud

    markdown = plaud._build_markdown(
        "Project Sync",
        "2026-04-26",
        {"summary": "Summary", "outline": "", "decisions": []},
        "Transcript",
    )

    assert render_entity_comment(plaud_entity_id("Project Sync", "2026-04-26")) in markdown
