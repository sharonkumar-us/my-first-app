import ollama

history = []

print("Local chatbot — type 'quit' to exit")

while True:
    user = input("\nYou: ")
    if user.lower() == "quit":
        break

    history.append({"role": "user", "content": user})
    reply = ollama.chat(model="qwen2.5-coder:7b", messages=history)
    text = reply["message"]["content"]
    history.append({"role": "assistant", "content": text})

    print(f"\nAI: {text}")