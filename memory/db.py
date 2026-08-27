"""Central Firestore client factory (post-undelete named-database support).

The project's ``(default)`` database was destroyed by the Day-7 teardown /
undelete cycle: the control-plane record survives (blocking re-creation) but
the data plane refuses to serve it ("database was deleted"). Live traffic
therefore rides a named database selected via
``DILIGENCE_FIRESTORE_DATABASE``. When the variable is unset (tests,
emulator, local dev) the default database is used and behavior is unchanged.
"""

from __future__ import annotations

import os

from google.cloud import firestore

LIVE_DATABASE_ENV = "DILIGENCE_FIRESTORE_DATABASE"
DEFAULT_DATABASE = "(default)"


def database_id() -> str:
    """Return the Firestore database id selected by the environment."""
    return os.environ.get(LIVE_DATABASE_ENV, DEFAULT_DATABASE)


def client_database(client: firestore.Client) -> str:
    """Return the database id *client* is bound to.

    The installed client library keeps the binding in ``_database`` with no
    public accessor; this seam keeps the private attribute in one place.
    """
    return str(client._database)


def make_client(project: str | None = None) -> firestore.Client:
    """Build a Firestore client bound to the configured database id.

    ``project=None`` resolves the project from the environment exactly like
    ``firestore.Client()`` does.
    """
    database = database_id()
    if project is None:
        return firestore.Client(database=database)
    return firestore.Client(project=project, database=database)
