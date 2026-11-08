import os

# Legacy UI fixtures are enabled explicitly in tests, never by application default.
os.environ.setdefault('EEYE_MOCK', '1')
