"""Serializable LangGraph state for ticket support and commerce requests."""

from typing import Any, Literal, TypedDict

RequestType = Literal["support_ticket", "product_order"]
ApprovalChoice = Literal["approve", "reject", "decline", "timeout"]
RunStatus = Literal[
    "running",
    "awaiting_approval",
    "awaiting_customer_selection",
    "approved",
    "rejected",
    "completed",
    "failed",
    "partially_completed",
    "timed_out",
    "step_limit_reached",
]


class ApprovalDecision(TypedDict):
    decision: ApprovalChoice
    operation_id: str


class ProductEvidence(TypedDict, total=False):
    product_id: str
    name: str
    source_url: str
    price_tnd: float
    availability: str
    retrieved_at: str


class TrajectoryEvent(TypedDict):
    node_name: str
    input_summary: str
    output_summary: str
    start_timestamp: str
    end_timestamp: str
    resulting_status: RunStatus


class AgentState(TypedDict, total=False):
    """Progressive state; unfilled data remains absent or ``None``."""

    run_id: str
    request_type: RequestType
    request_text: str
    ticket_id: str
    customer_id: str
    product_query: str
    product_prompt_parser: Literal["llm", "rules_fallback", "provided"]
    price_min_tnd: float | None
    price_max_tnd: float | None
    product_criteria: dict[str, Any]
    step_count: int
    status: RunStatus
    ticket: dict[str, Any] | None
    customer: dict[str, Any] | None
    order: dict[str, Any] | None
    products: list[ProductEvidence]
    selected_products: list[dict[str, Any]]
    draft: dict[str, Any] | None
    proposed_actions: list[dict[str, Any]]
    approval: ApprovalDecision | None
    operation_id: str | None
    tool_calls: list[dict[str, Any]]
    errors: list[str]
    trajectory: list[TrajectoryEvent]
    applied_actions: list[dict[str, Any]]
