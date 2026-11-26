"""⏳ A proposal waiting for Apply that can't be reached any more goes grey (mainapp/bulba/flow.py expire_unreachable)."""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from mainapp.bulba import flow


def prop(pid, kind="preset", **payload):
    return {"id": pid, "kind": kind, "title": pid, "status": "pending", "payload": payload}


class ExpireTests(SimpleTestCase):
    def test_a_card_gone_from_the_conversation(self):
        s = SimpleNamespace(events=[{"type": "proposal", "id": "a"}], proposals=[prop("a"), prop("b")], chat=None)
        self.assertTrue(flow.expire_unreachable(s))
        self.assertEqual([p["status"] for p in s.proposals], ["pending", "expired"])
        self.assertFalse(flow.expire_unreachable(s))  # once
        s.proposals.append(prop("c"))  # made mid-turn: its card comes with the turn's end, so the prompt leaves it be
        self.assertNotIn("WAITING FOR APPLY right now: “a”; “b”", flow.proposals_section(s))
        self.assertIn("WAITING FOR APPLY right now: “a”; “c”", flow.proposals_section(s))

    def test_a_fix_for_a_chat_message_that_changed(self):
        s = SimpleNamespace(events=[{"type": "proposal", "id": "f"}, {"type": "proposal", "id": "g"}], chat=object(),
                            proposals=[prop("f", "message_fix", index=0, original="old words", text="new"),
                                       prop("g", "message_fix", index=1, original="still here", text="new")])
        msgs = [["assistant", "x", "edited since"], ["assistant", "x", "still here"]]
        with mock.patch("mainapp.chats.read", return_value={"messages": msgs}):
            flow.expire_unreachable(s)
        self.assertEqual([p["status"] for p in s.proposals], ["expired", "pending"])
        self.assertIn("changed", s.proposals[0]["why"])
