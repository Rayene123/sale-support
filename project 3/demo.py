"""Run the offline human-approval workflow demonstration."""

from agent import tools
from agent.graph import run_ticket


def main() -> None:
    print("=== SCENARIO A: APPROVAL ===\n")
    tools.reset_write_log()
    print("Starting agent...\n")
    paused = run_ticket("TICKET-102")
    print(f"Ticket retrieved: {paused['ticket']['ticket_id']}: {paused['ticket']['subject']}")
    print(f"Customer retrieved: {paused['customer']['customer_id']}: {paused['customer']['name']}")
    print(f"Order retrieved: {paused['order']['order_id']}: {paused['order']['status']}\n")
    print("Action proposed:")
    print(f"Status: {paused['draft']['proposed_status']}")
    print(f"Labels: {', '.join(paused['draft']['proposed_labels'])}\n")
    print("Agent paused for human approval.\n")
    print(f"Database writes before approval: {len(tools.WRITE_LOG)}\n")
    print("Human decision: APPROVE\n")
    print("Executing approved database update...\n")
    completed = run_ticket(
        "TICKET-102",
        {"decision": "approve", "operation_id": paused["draft"]["operation_id"]},
        run_id=paused["run_id"],
    )
    print(f"Final status: {completed['status']}\n")
    print(f"Database writes after approval: {len(tools.WRITE_LOG)}")
    print("Applied actions:")
    print(completed["applied_actions"])
    print("WRITE_LOG:")
    print(tools.WRITE_LOG)

    print("\n=== SCENARIO B: REJECTION ===\n")
    tools.reset_write_log()
    rejected_checkpoint = run_ticket("TICKET-102")
    print("Agent paused for human approval.\n")
    print("Human decision: REJECT\n")
    rejected = run_ticket(
        "TICKET-102",
        {"decision": "reject", "operation_id": rejected_checkpoint["draft"]["operation_id"]},
        run_id=rejected_checkpoint["run_id"],
    )
    print(f"Final status: {rejected['status']}\n")
    print(f"Database writes: {len(tools.WRITE_LOG)}")


if __name__ == "__main__":
    main()
