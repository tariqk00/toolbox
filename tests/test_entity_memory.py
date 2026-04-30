
import unittest
from unittest.mock import MagicMock, patch
from toolbox.lib.entity_memory import EntityMemory

class TestEntityMemory(unittest.TestCase):
    def test_parse_and_render(self):
        content = """# Test Entity
<!-- entity_id: test_123 -->

## Summary
A test entity for schema validation.

## Structured Fields
- **Account:** ...1234
- **Vendor:** TestCorp

## Timeline
- **2026-04-01:** Entity created.
- **2026-04-15:** Entity updated.

## Sources
- email_123
- drive_456

## Conflicts
- None

## Links
- other_entity_789
"""
        em = EntityMemory.parse(content)
        self.assertEqual(em.name, "Test Entity")
        self.assertEqual(em.entity_id, "test_123")
        self.assertEqual(em.summary, "A test entity for schema validation.")
        self.assertEqual(em.fields["Account"], "...1234")
        self.assertEqual(em.fields["Vendor"], "TestCorp")
        self.assertEqual(len(em.timeline), 2)
        self.assertEqual(em.timeline[0], "- **2026-04-01:** Entity created.")
        
        rendered = em.render()
        self.assertIn("# Test Entity", rendered)
        self.assertIn("<!-- entity_id: test_123 -->", rendered)
        self.assertIn("## Summary\nA test entity for schema validation.", rendered)
        self.assertIn("- **Account:** ...1234", rendered)
        self.assertIn("## Timeline\n- **2026-04-01:** Entity created.\n- **2026-04-15:** Entity updated.", rendered)

    def test_empty_skeleton(self):
        em = EntityMemory("New Entity", "new_001")
        rendered = em.render()
        self.assertIn("# New Entity", rendered)
        self.assertIn("*(No summary provided)*", rendered)
        self.assertIn("*(No events recorded)*", rendered)

    def test_update_methods(self):
        em = EntityMemory("Update Test")
        em.set_summary("New summary")
        em.set_field("Key", "Value")
        em.add_timeline_event("New event", date="2026-04-29")
        em.add_source("Source A")
        em.add_link("Link B")
        
        rendered = em.render()
        self.assertIn("New summary", rendered)
        self.assertIn("- **Key:** Value", rendered)
        self.assertIn("- **2026-04-29:** New event", rendered)
        self.assertIn("- Source A", rendered)
        self.assertIn("- Link B", rendered)

if __name__ == "__main__":
    unittest.main()
