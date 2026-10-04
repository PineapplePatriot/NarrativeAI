"""
Bulba, the setup assistant: a talking potato that sets up NarrativeAI through conversation.

- agent.py    the conversation loop, Bulba's instructions and the tools it can call
- actions.py  what happens when you press Apply (and Undo) on one of its proposals

Bulba runs on a model we choose (ai_client.BULBA_MODEL) through the user's OpenRouter key.
Every writing sample it shows comes from the model the user will actually chat with.
"""
