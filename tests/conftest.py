import os

# Must be set before any project imports so rag_engine skips native C extensions
os.environ.setdefault("FIXAGO_TEST_MODE", "1")
