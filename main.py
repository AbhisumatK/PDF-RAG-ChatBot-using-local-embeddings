import streamlit as st
import os
from data_loader import DataLoader
from vector_db import VectorDB # Using the new class name
from groq import Groq
import tempfile

# Page configuration
st.set_page_config(page_title="PDF RAG - Local Embeddings", layout="wide")

# Initialize session state for tracking current file
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_file_name" not in st.session_state:
    st.session_state.current_file_name = None

# Constants
COLLECTION_NAME = "pdf_docs"

# Load models
@st.cache_resource
def get_loader():
    """Heavy model loading - cached for performance."""
    return DataLoader()

# Initialize resources
loader = get_loader()
# Fresh DB instance to avoid caching issues with class changes
db = VectorDB(collection_name=COLLECTION_NAME, dimension=loader.embedding_dimension)


# Groq client
if 'GROQ_API_KEY' not in st.secrets:
    st.sidebar.error("GROQ_API_KEY not found in secrets. Please add it to .streamlit/secrets.toml")
    st.stop()

client = Groq(api_key=st.secrets['GROQ_API_KEY'])

# Sidebar
st.sidebar.title("PDF Assistant")
uploaded_file = st.sidebar.file_uploader("Upload a PDF", type="pdf")

# Logic to handle NEW file upload
if uploaded_file is not None:
    # If the file name is different from what we last processed, reset everything!
    if uploaded_file.name != st.session_state.current_file_name:
        with st.sidebar:
            with st.status("Processing the new PDF...", expanded=True) as status:
                # 1. Clear old data
                st.write("Clearing previous document data...")
                db.reset_database()
                st.session_state.messages = [] # Reset chat history too
                
                # 2. Save uploaded file to temp
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name

                try:
                    # 3. Load and split
                    st.write("Extracting text...")
                    text = loader.load_pdf(tmp_file_path)
                    
                    if not text:
                        status.update(label="No text extracted!", state="error", expanded=True)
                        st.error("Could not extract any text from this PDF. It might be a scanned image (OCR required) or encrypted.")
                        st.stop()
                    
                    st.write(f"Extracted {len(text)} characters.")


                    chunks = loader.split_text(text)
                    if not chunks:
                        status.update(label="No chunks created!", state="error", expanded=True)
                        st.error("The document contains text but it couldn't be split into chunks.")
                        st.stop()
                    
                    # 4. Embed and store
                    st.write(f"Generating embeddings for {len(chunks)} chunks...")
                    vectors = loader.get_embeddings(chunks)
                    payloads = [{"text": chunk, "source": uploaded_file.name} for chunk in chunks]
                    
                    st.write(f"Upserting {len(chunks)} chunks to ChromaDB...")
                    db.upsert(vectors, payloads)
                    
                    # Update state
                    st.session_state.current_file_name = uploaded_file.name
                    status.update(label=f"Done! Chatting with {uploaded_file.name}", state="complete", expanded=False)
                except Exception as e:
                    status.update(label="Error processing PDF!", state="error", expanded=True)
                    st.error(f"An error occurred: {e}")
                finally:
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)


if st.sidebar.button("Clear History"):
    st.session_state.messages = []
    st.rerun()

# Main Chat Interface
st.title("Chat with your PDF")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask something about the document"):
    if not st.session_state.current_file_name:
        st.warning("Please upload a PDF first!")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            query_vector = loader.get_embeddings([prompt])[0]
            search_results = db.search(query_vector, top_k=3)
            context = "\n\n".join(search_results["contexts"])
            
            system_prompt = f"""
            You are a helpful assistant. Use the following pieces of retrieved context to answer the user's question.
            If you don't know the answer based on the context, just say that you don't know. No preamble.
            
            Context:
            {context}
            """
            
            try:
                completion = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                )
                response = completion.choices[0].message.content
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Error calling Groq API: {e}")
