"""Chatbot placeholder.

`get_response` is the seam for a future LLM integration: swap its body
for a real API call while keeping the same signature (question, report)
and callers in app.py won't need to change.
"""

GENERIC_RESPONSE = (
    "Thanks for your question! This is a placeholder response from Discovr's "
    "assistant. Once connected to a real AI backend, you'll get a tailored "
    "answer based on your specific AI-visibility report."
)


def get_response(question, report=None):
    return GENERIC_RESPONSE
