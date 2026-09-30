from langchain.text_splitter import RecursiveCharacterTextSplitter, SentenceTransformersTokenTextSplitter

from llm_engineering.application.networks import EmbeddingModelSingleton

ARTICLE_CHUNK_SIZE = 1500
ARTICLE_CHUNK_OVERLAP = 150


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    embedding_model = EmbeddingModelSingleton()
    character_splitter = RecursiveCharacterTextSplitter(separators=["\n\n"], chunk_size=chunk_size, chunk_overlap=0)
    text_split_by_characters = character_splitter.split_text(text)

    token_splitter = SentenceTransformersTokenTextSplitter(
        chunk_overlap=chunk_overlap,
        tokens_per_chunk=embedding_model.max_input_length,
        model_name=embedding_model.model_id,
    )
    chunks_by_tokens = []
    for section in text_split_by_characters:
        chunks_by_tokens.extend(token_splitter.split_text(section))

    return chunks_by_tokens


def chunk_document(
    text: str,
    chunk_size: int = ARTICLE_CHUNK_SIZE,
    chunk_overlap: int = ARTICLE_CHUNK_OVERLAP,
) -> list[str]:
    """Alias for chunk_article()."""

    return chunk_article(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def chunk_article(
    text: str,
    chunk_size: int = ARTICLE_CHUNK_SIZE,
    chunk_overlap: int = ARTICLE_CHUNK_OVERLAP,
) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]
