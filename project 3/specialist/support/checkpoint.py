"""Process-persistent LangGraph checkpoint storage for local runs."""

from langgraph.checkpoint.memory import InMemorySaver

# One saver per Python process allows a web form or CLI call to resume a run.
# Production deployments should replace this with a durable shared checkpointer.
CHECKPOINTER = InMemorySaver()


def graph_config(run_id: str) -> dict:
    """Return the stable LangGraph thread config for a run."""
    return {"configurable": {"thread_id": run_id}}
