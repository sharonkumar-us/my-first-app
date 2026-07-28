import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL"),
    api_key=os.getenv("OLLAMA_API_KEY"),
)

print("Streaming response:\n")

stream = client.chat.completions.create(
    model="qwen2.5-coder:7b",
    messages=[
        {"role": "user", "content": "Explain in 3 sentences what a health insurance deductible is."}
    ],
    stream=True,
)

for chunk in stream:
    token = chunk.choices[0].delta.content
    if token:
        print(token, end="", flush=True)

print("\n\nStream complete.")