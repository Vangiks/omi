"""Unit tests for the deferred-conversation filter in the listen-session sweeper.

Conversations with `deferred=True` sit in status=processing until opened; the sweeper must
not re-send them to pusher.
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture(scope='module')
def conversations_db():
    import database.conversations as cdb

    return cdb


class TestDeferredNotRequeuedBySweeper:
    """Deferred conversations sit in status=processing until opened — they must NOT be returned by
    get_processing_conversations (the listen-session sweeper re-sends those to pusher, which would
    background-process deferred rows and defeat the cost saving)."""

    def test_get_processing_conversations_excludes_deferred(self, conversations_db):
        def _doc(d):
            m = MagicMock()
            m.to_dict.return_value = d
            return m

        docs = [
            _doc({'id': 'a', 'deferred': True}),  # deferred -> excluded
            _doc({'id': 'b', 'deferred': False}),  # not deferred -> kept
            _doc({'id': 'c'}),  # no deferred field (normal processing) -> kept
        ]
        chain = MagicMock()
        chain.stream.return_value = docs
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value.where.return_value = chain
        with __import__('unittest.mock', fromlist=['patch']).patch.object(conversations_db, 'db', mock_db):
            result = conversations_db.get_processing_conversations('uid-x')
        assert [c['id'] for c in result] == ['b', 'c']
