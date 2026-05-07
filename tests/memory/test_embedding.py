"""Tests for EmbeddingService."""
from unittest.mock import MagicMock

from app.memory.embedding import EmbeddingService


class TestEmbeddingService:
    def test_embed_single_text(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2, 0.3]),
        ]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService(client=mock_client, model="test-model")
        result = service.embed("hello world")

        assert result == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once_with(
            model="test-model",
            input=["hello world"],
        )

    def test_embed_batch(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2]),
            MagicMock(embedding=[0.3, 0.4]),
        ]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService(client=mock_client, model="test-model")
        results = service.embed_batch(["text one", "text two"])

        assert results == [[0.1, 0.2], [0.3, 0.4]]
        mock_client.embeddings.create.assert_called_once_with(
            model="test-model",
            input=["text one", "text two"],
        )

    def test_embed_empty_text(self):
        mock_client = MagicMock()
        service = EmbeddingService(client=mock_client)

        result = service.embed("")
        assert result is None

        result = service.embed("   ")
        assert result is None

    def test_embed_api_failure_returns_none(self):
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = RuntimeError("API down")

        service = EmbeddingService(client=mock_client)
        result = service.embed("hello")
        assert result is None

    def test_embed_batch_with_empty_and_cache(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.5, 0.6]),
        ]
        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService(client=mock_client)

        # First call: embed the text
        results = service.embed_batch(["hello", ""])
        assert results[0] == [0.5, 0.6]
        assert results[1] is None

        # Second call with same text should hit cache
        results = service.embed_batch(["hello"])
        assert results[0] == [0.5, 0.6]
        # API should only be called once (first call)
        assert mock_client.embeddings.create.call_count == 1
