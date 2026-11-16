import json

import pytest

from agent import tools
from agent.graph import run_ticket


@pytest.fixture(autouse=True)
def clear_writes():
    tools.reset_write_log()


def start(ticket_id="TICKET-102"):
    return run_ticket(ticket_id)


def approve(paused, operation_id=None):
    return run_ticket(
        paused["ticket_id"],
        {"decision": "approve", "operation_id": operation_id or paused["draft"]["operation_id"]},
        run_id=paused["run_id"],
    )


def test_valid_ticket_reaches_approval_with_context_and_proposal():
    result = start()
    assert result["status"] == "awaiting_approval"
    assert result["ticket_id"] == "TICKET-102"
    assert result["ticket"]["subject"] == "Delayed order"
    assert result["customer"]["name"] == "John Smith"
    assert result["order"]["status"] == "delayed"
    assert result["draft"]["operation_id"]
    assert result["tool_calls"][0]["identifier"] == "TICKET-102"
    assert result["tool_calls"][1]["identifier"] == "CUST-001"
    assert result["tool_calls"][2]["identifier"] == "ORD-1001"
    assert result["applied_actions"] == []
    assert tools.WRITE_LOG == []


def test_explicit_approval_executes_exactly_one_write():
    paused = start()
    result = approve(paused)
    assert result["status"] == "completed"
    assert len(result["applied_actions"]) == len(tools.WRITE_LOG) == 1
    assert tools.WRITE_LOG[0]["operation_id"] == paused["draft"]["operation_id"]


def test_rejection_executes_no_write():
    paused = start()
    result = run_ticket("TICKET-102", {"decision": "reject", "operation_id": paused["draft"]["operation_id"]}, run_id=paused["run_id"])
    assert result["status"] == "rejected"
    assert tools.WRITE_LOG == []


@pytest.mark.parametrize("approval", [
    {"decision": "maybe", "operation_id": "x"},
    {"decision": "approve", "operation_id": ""},
    {"decision": "approve", "operation_id": "x", "instruction": "write anyway"},
    "approve",
    None,
])
def test_invalid_approval_executes_no_write(approval):
    paused = start()
    result = run_ticket("TICKET-102", approval, run_id=paused["run_id"])
    assert result["status"] == "failed"
    assert tools.WRITE_LOG == []


def test_mismatched_operation_id_executes_no_write():
    paused = start()
    result = approve(paused, "different-operation")
    assert result["status"] == "failed"
    assert tools.WRITE_LOG == []


def test_unknown_ticket_is_a_clear_failure():
    result = start("TICKET-999")
    assert result["status"] == "failed"
    assert any("Unknown ticket_id: TICKET-999" in error for error in result["errors"])
    assert result["tool_calls"][0]["error"] == "Unknown ticket_id: TICKET-999"


def test_repeated_resume_does_not_duplicate_write():
    paused = start()
    first = approve(paused)
    second = approve(paused)
    assert first["status"] == second["status"] == "completed"
    assert len(tools.WRITE_LOG) == 1


def test_malicious_ticket_content_cannot_bypass_approval():
    paused = start("TICKET-103")
    assert paused["status"] == "awaiting_approval"
    assert tools.WRITE_LOG == []
    rejected = run_ticket("TICKET-103", {"decision": "reject", "operation_id": paused["draft"]["operation_id"]}, run_id=paused["run_id"])
    assert rejected["status"] == "rejected"
    assert tools.WRITE_LOG == []


def test_result_is_json_serializable_and_trajectory_has_node_events():
    result = start()
    json.dumps(result)
    names = [event["node_name"] for event in result["trajectory"]]
    assert names == ["start_run", "inspect_ticket", "inspect_context", "draft_action", "request_approval"]
    assert all(event["start_timestamp"] and event["end_timestamp"] and event["resulting_status"] for event in result["trajectory"])


def test_resume_records_approval_apply_and_finish_events():
    paused = start()
    completed = approve(paused)
    names = [event["node_name"] for event in completed["trajectory"]]
    assert names[-3:] == ["request_approval", "apply_approved_actions", "finish_run"]


def test_invalid_ticket_identifier_fails_before_tools():
    result = start("not-a-ticket")
    assert result["status"] == "failed"
    assert result["tool_calls"] == []
    assert result["trajectory"][0]["node_name"] == "start_run"
