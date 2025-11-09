import re
import unicodedata
from collections import Counter
from pathlib import Path

file_path = "speaker.txt"   # change if needed
text = Path(file_path).read_text(encoding="utf-8", errors="ignore")

# 1) Extract the bracket chunk before the colon (speaker/action header)
header_re = re.compile(r"^\[\s*([^\]]+?)\s*:\]", flags=re.MULTILINE)
raw_headers = header_re.findall(text)

def normalize_header_to_name(h: str,
                             strip_actions=True,
                             strip_emojis_symbols=True,
                             strip_trailing_punct=True):
    """Turn a bracket header into a canonical speaker name."""
    # Unicode normalize
    s = unicodedata.normalize("NFKC", h)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    tokens = s.split(" ")

    # Heuristic: trim trailing all-lowercase "action" words (generalizes)
    if strip_actions:
        def has_non_lower(ts):  # keep at least one non-lower token
            return any(not re.fullmatch(r"[a-z]+", t) for t in ts)
        while tokens and re.fullmatch(r"[a-z]+", tokens[-1]):
            if has_non_lower(tokens[:-1]):
                tokens.pop()
            else:
                break
        s = " ".join(tokens).strip()

    # Standardize apostrophes/quotes
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')

    # Optionally strip emojis / symbols from ends & middles (keep letters, digits, spaces, and common name punctuation)
    if strip_emojis_symbols:
        # keep letters, numbers, space and - . ' & (common in names); drop everything else
        s = re.sub(r"[^0-9A-Za-z\s\.\-\'&]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()

    # Optionally strip trailing punctuation (. , : ; ! ? … -)
    if strip_trailing_punct:
        s = re.sub(r"[.,:;!?\u2026\-–—]+$", "", s).strip()

    # Collapse multiple dots in initials (e.g., "J. R. R." stays fine)
    s = re.sub(r"\s*\.\s*", ".", s)  # tighten "A . B ." -> "A.B."
    s = re.sub(r"\s+", " ", s).strip()

    return s

# 2) Normalize all headers -> names
names = [normalize_header_to_name(h) for h in raw_headers if h.strip()]

# 3) Count occurrences (merged by canonicalization)
counts = Counter(names)

# 4) Print nicely
print("Speaker List and Counts (canonicalized):\n")
for speaker, count in counts.most_common():
    print(f"{speaker}: {count}")

print("\nUnique Speakers:\n", sorted(counts.keys(), key=str.casefold))

