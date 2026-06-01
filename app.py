from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.readers.file import PDFReader


# for pdf reader
file_extractor = {
    ".pdf": PDFReader()
}

#Load documents
documents = SimpleDirectoryReader('data', file_extractor=file_extractor).load_data()

#Local embedding model
embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")

#Local LLM
llm = Ollama(model="llama3")

#Create index
index = VectorStoreIndex.from_documents(documents, embed_model=embed_model)

#Query Engine
query_engine = index.as_query_engine(llm=llm)

print("\n Chatbot ready!, ask any questions based on My Resume.  Type 'exit' to quit.\n")

while True:
    query = input("You: ")
    if query.lower() == 'exit':
        print("Goodbye!")
        break
    response = query_engine.query(query)
    print(f"Chatbot: {response}\n")
