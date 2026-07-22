def manual_recursive_split(text, chunk_size=500, chunk_overlap=50):
    """A simplified version of what RecursiveCharacterTextSplitter does internally."""
    separators = ["\n\n", "\n", ". ", " ", ""]

    def split_text(text, seps):
        if len(text) <= chunk_size:
            return [text]
        sep = seps[0]
        remaining_seps = seps[1:]
        if sep == "":
            # Last resort: hard split by character count
            return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

        parts = text.split(sep)
        chunks = []
        current = ""
        for part in parts:
            candidate = current + sep + part if current else part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If a single part is still too big, recurse into finer separators
                if len(part) > chunk_size:
                    chunks.extend(split_text(part, remaining_seps))
                    current = ""
                else:
                    current = part
        if current:
            chunks.append(current)
        return chunks

    raw_chunks = split_text(text, separators)

    # Apply overlap
    overlapped = []
    for i, chunk in enumerate(raw_chunks):
        if i == 0:
            overlapped.append(chunk)
        else:
            prev_tail = raw_chunks[i-1][-chunk_overlap:]
            overlapped.append(prev_tail + chunk)
    return overlapped


# --- Test on one of Day 5's real files ---
with open("raw_text/benefits.txt", "r", encoding="utf-8") as f:
    sample_text = f.read()

manual_chunks = manual_recursive_split(sample_text, chunk_size=500, chunk_overlap=50)

print(f"Manual splitter: {len(manual_chunks)} chunks")
for i, c in enumerate(manual_chunks):
    print(f"\n--- Chunk {i+1} ({len(c)} chars) ---")
    print(c)
    from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
library_chunks = splitter.split_text(sample_text)

print(f"\n\nLibrary splitter: {len(library_chunks)} chunks")
for i, c in enumerate(library_chunks):
    print(f"\n--- Library Chunk {i+1} ({len(c)} chars) ---")
    print(c)