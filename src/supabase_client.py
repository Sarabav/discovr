"""A cached Supabase client, used by src/supabase_store.py.

Uses the service-role key (SUPABASE_API_KEY) rather than the anon key so
the app's own reads/writes are never blocked by row-level security --
this process is a trusted backend, not a browser client.
"""

import os

_client = None


def get_client():
    global _client
    if _client is None:
        from supabase import create_client

        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_API_KEY"]
        _client = create_client(url, key)
    return _client
