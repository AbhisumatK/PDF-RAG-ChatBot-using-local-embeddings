import chromadb
from chromadb.config import Settings
import uuid

class VectorDB:
    def __init__(self, collection_name="documents", path="chroma_storage", dimension=384):
        self.client = chromadb.PersistentClient(path=path)
        self.collection_name = collection_name
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def reset_database(self):
        """Deletes and recreates the collection to ensure a clean state."""
        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:
            pass # Collection might not exist yet
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def upsert(self, vectors, payloads, batch_size=100):
        """
        Upserts vectors and payloads into the collection in batches.
        Prevents memory issues and API limits for large documents.
        """
        total = len(vectors)
        for i in range(0, total, batch_size):
            end = min(i + batch_size, total)
            batch_vectors = vectors[i:end]
            batch_payloads = payloads[i:end]
            
            ids = [str(uuid.uuid4()) for _ in range(len(batch_vectors))]
            documents = [p.get("text", "") for p in batch_payloads]
            metadatas = [{"source": p.get("source", "Unknown")} for p in batch_payloads]
            
            self.collection.add(
                embeddings=batch_vectors,
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
        print(f"Successfully indexed {total} chunks in batches of {batch_size}.")


    def search(self, query_vector, top_k=5):
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k
        )
        
        contexts = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        sources = list(set([m.get("source", "Unknown") for m in metadatas]))

        return {"contexts": contexts, "sources": sources}
