"""
indexer.py — Document loading and vector index construction.

Reads from DATA_DIR, chunks documents, embeds them with the HuggingFace model,
and persists the index to PERSIST_DIR so startup is fast on subsequent runs.
"""

import logging

from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from config import DATA_DIR, DATA_SUBDIRS, EMBED_MODEL, PERSIST_DIR, SUPPORTED_EXTS

logger = logging.getLogger(__name__)


def collect_documents() -> list:
    """
    Walk DATA_DIR sub-folders and load all supported files.
    Falls back to a flat DATA_DIR read if no sub-folders are present.
    """
    subdirs_found = [
        str(DATA_DIR / sub)
        for sub in DATA_SUBDIRS
        if (DATA_DIR / sub).exists() and any((DATA_DIR / sub).glob("**/*"))
    ]

    if subdirs_found:
        all_docs = []
        for d in subdirs_found:
            docs = SimpleDirectoryReader(
                d, recursive=True, required_exts=SUPPORTED_EXTS
            ).load_data()
            logger.info("  %s → %d document(s)", d, len(docs))
            all_docs.extend(docs)
        return all_docs

    logger.info("No sub-folders found — reading %s directly", DATA_DIR)
    return SimpleDirectoryReader(
        str(DATA_DIR), recursive=True, required_exts=SUPPORTED_EXTS
    ).load_data()


def build_index() -> VectorStoreIndex:
    """
    Build or load the vector index.

    If PERSIST_DIR exists the cached index is loaded (fast path).
    Otherwise documents are loaded, chunked, embedded, and persisted.
    Delete PERSIST_DIR to force a full rebuild.
    """
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL)
    Settings.llm = None  # LLM calls are handled by llm.py, not LlamaIndex

    if PERSIST_DIR.exists():
        logger.info("Loading index from cache at %s", PERSIST_DIR)
        return load_index_from_storage(
            StorageContext.from_defaults(persist_dir=str(PERSIST_DIR))
        )

    logger.info("Building index from %s …", DATA_DIR)
    if not DATA_DIR.exists():
        raise FileNotFoundError(
            f"'{DATA_DIR}' folder not found. "
            "Create it with sub-folders: resume/, bio/, projects/, blog/, github/"
        )

    documents = collect_documents()
    if not documents:
        raise FileNotFoundError(
            f"No supported files ({SUPPORTED_EXTS}) found under {DATA_DIR}/. "
            "Add your documents and restart."
        )
    logger.info("Total documents loaded: %d", len(documents))

    # chunk_size and chunk_overlap are tuned for mixed doc types — do not change
    splitter = SentenceSplitter(chunk_size=600, chunk_overlap=80)
    nodes = splitter.get_nodes_from_documents(documents)
    logger.info("Split into %d chunks", len(nodes))

    index = VectorStoreIndex(nodes)
    index.storage_context.persist(persist_dir=str(PERSIST_DIR))
    logger.info("Index persisted to %s", PERSIST_DIR)
    return index
