import os
from huggingface_hub import InferenceClient
import streamlit as st

hf_access_token = st.secrets.get("HF_ACCESS_TOKEN")

client = InferenceClient(
    provider="hf-inference",
    api_key=hf_access_token,
)

result = client.feature_extraction(
    "Today is a sunny day",
    model="Qwen/Qwen3-Embedding-0.6B",
)
print(result)