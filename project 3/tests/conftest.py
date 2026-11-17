"""Keep the ordinary test suite offline and independent of developer secrets."""
import os

# graph.py loads dotenv at import time. Disable that before test collection so
# a developer's OPENAI_API_KEY can never cause ordinary graph tests to call an
# external model service.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.pop("OPENAI_API_KEY", None)
