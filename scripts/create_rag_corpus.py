#!/usr/bin/env python3
"""Script to create a serverless Vertex AI RAG corpus and import pg49513.txt."""

from vertexai.preview import rag
from vertexai.preview.rag.utils import resources as rr
import vertexai

PROJECT_ID = "qwiklabs-gcp-03-4c89eb0d0a8d"
LOCATION = "us-central1"
GCS_PATH = "gs://wealthpulse-assets-qwiklabs-gcp-03-4c89eb0d0a8d/rag/pg49513.txt"

PARSING_PROMPT = (
    "Extract the individual useful facts, remedies, and herbal notes described in this text. "
    "Ignore and omit all metadata, boilerplate, licensing, and table of contents. "
    "Output clean, self-contained prose."
)


def main():
    print(f"Initializing Vertex AI for project={PROJECT_ID}, location={LOCATION}...")
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    print("Configuring Serverless RAG managed DB...")
    cfg = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragEngineConfig"
    rag.update_rag_engine_config(
        rag_engine_config=rag.RagEngineConfig(
            name=cfg,
            rag_managed_db_config=rag.RagManagedDbConfig(mode=rr.Serverless()),
        )
    )

    print("Creating RAG corpus 'complete-herbal-corpus'...")
    corpus = rag.create_corpus(
        display_name="complete-herbal-corpus",
        embedding_model_config=rag.EmbeddingModelConfig(
            publisher_model="publishers/google/models/text-embedding-005"
        ),
    )
    print(f"Created corpus: {corpus.name}")

    print(f"Importing and indexing {GCS_PATH} into corpus...")
    resp = rag.import_files(
        corpus_name=corpus.name,
        paths=[GCS_PATH],
        transformation_config=rag.TransformationConfig(
            chunking_config=rag.ChunkingConfig(chunk_size=512, chunk_overlap=100)
        ),
        llm_parser=rag.LlmParserConfig(
            model_name="gemini-2.5-flash",
            custom_parsing_prompt=PARSING_PROMPT,
        ),
    )
    print(f"Import complete! Imported files count: {resp.imported_rag_files_count}")

    # Write corpus name to a file for reference
    with open("rag_corpus_info.txt", "w") as f:
        f.write(corpus.name)
    print(f"Saved corpus name to rag_corpus_info.txt: {corpus.name}")


if __name__ == "__main__":
    main()
