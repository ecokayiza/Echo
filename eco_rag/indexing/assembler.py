import os

from ..chat.registry import normalize_embedding_model_settings
from ..config import Config
from ..domain.schema import RAGRecord, RAGMetadata, ExtraAttributes
from .database_registry import DatabaseSettings, resolve_database_embedding_settings

# This is the interface for outer files
# provide APIs to finish one whole process like:
# v  1.store_file:     filepath -> load -> chunk -> embed -> assemble records -> DB
# x  2.query_file:     filepath -> query file in DB -> return results
# x  3.delete_file:    filepath -> find records in DB -> delete records
##############################################

# === Handles file process and interaction with vector DB ===
class Assembler:
    # === Components ===
    def __init__(self, vector_db, data_loader, chunker, embedder, *, database: DatabaseSettings | None = None):
        self.db = vector_db
        self.data_loader = data_loader
        self.chunker = chunker
        self.embedder = embedder
        self.database = database
    
    def store_file(self, filepath):
        """
        Store file to vdb.
        filepath: should be absolute path.
        """
        records = self._get_records(filepath)
        self._records_to_db(records)
    
    def delete_file(self, filepath):
        """
        Delete file from vdb.
        filepath: should be absolute path.
        """
        rel_path = Config.get_relative_path(filepath)
        where = {"file_path": rel_path}
        self.db.delete_documents(where)
        
    def query_file(self, filepath):
        """
        Query file from vdb.
        Args:
            filepath: should be absolute path.
        Returns:
            A dictionary with query results, *no distance included* since we query by filters
            like {'document_ids': [...], 'documents': [...], 'metadatas': [...]}
        """
        rel_path = Config.get_relative_path(filepath)
        where = {"file_path": rel_path}
        results = self.db.query_by_metadata(where, n_results=None)
        print(f"Found {len(results.get('documents', []))} documents for file: {rel_path}")
        return results
    
    def query_with_vector(self, vector, n_results=5, where=None):
        """
        Query similar documents based on **one** query vector
        """
        results = self.db.query_with_vector(vector, n_results, where)
        # results['documents'] is a list of lists, so we check the length of the first list
        doc_count = len(results.get('documents', [[]])[0])
        print(f"Found {doc_count} documents for the query vector.")
        return results
    
    def _get_records(self, file_path):
        """
        Get records objects from file_path, to create a record, we need:
            chunk text, embedding vector, metadata
        """
        _, ext = os.path.splitext(file_path)
        data = self.data_loader.load(file_path)
        chunks = self.chunker.chunk(data, ext)
        embedding_settings = resolve_database_embedding_settings(self.database) if self.database is not None else None
        embeddings = self.embedder.embed_documents(
            chunks,
            normalize_embedding_model_settings(embedding_settings) if embedding_settings is not None else None,
        )
        
        records = []
        for idx, chunk in enumerate(chunks):
 
            metadata = RAGMetadata(
                source_name=os.path.basename(file_path),
                source_type=ext.lstrip('.'),
                attributes=ExtraAttributes(
                    file_path=Config.get_relative_path(file_path),
                    chunk_index=idx
                )
            )
            record = RAGRecord(
                document=chunk,
                metadata=metadata,
                vector=embeddings[idx]
            )
            records.append(record)
        return records
    
    def _records_to_db(self, records):
        """
        Insert records to vector DB
        """
        formatted_records = [r.to_db_format() for r in records]
        
        if formatted_records:
            self.db.add_documents(
                ids=[r["id"] for r in formatted_records],
                texts=[r["document"] for r in formatted_records],
                embeddings=[r["vector"] for r in formatted_records],
                metadatas=[r["metadata"] for r in formatted_records]
            )
    
if __name__ == "__main__":
    from .loader import DataLoaderFactory
    from .chunker import ChunkerFactory
    from .embedder import OpenAICompatibleEmbedder
    from .vector_database import VectorDatabase

    file_path = Config.TEST_FILE_PATH
    vector_db = VectorDatabase()
    data_loader = DataLoaderFactory()
    chunker = ChunkerFactory()
    embedder = OpenAICompatibleEmbedder()
    assembler = Assembler(vector_db, data_loader, chunker, embedder)
    
    # print("Dpocument count in DB before storing file:", assembler.db.count())
    # assembler.store_file(file_path)
    # print("Document count in DB after storing file:", assembler.db.count())
    
    # print("Document count in DB before deleting file:", assembler.db.count())
    # assembler.delete_file(file_path)
    # print("Document count in DB after deleting file:", assembler.db.count())
    
    # results = assembler.query_file(file_path)
    # records = RAGRecord.get_records_from_results(results)
    
    text = ["智能体采取的动作"]
    embedding = embedder.embed(text)[0]
    results = assembler.query_with_vector(embedding, n_results=5)
    records = RAGRecord.get_records_from_results(results)
    
    for record in records:
        record.print()
