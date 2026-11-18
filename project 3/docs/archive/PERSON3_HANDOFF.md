# Person 3 Handoff — Evaluation, Errors, and Threat Model

The combined branch includes Person 1's graph checks and Person 2's tool fixes.
Run `python -m eval.run` and `python -m pytest -q` from the Project 3 directory.

The evaluator runs 36 workflow scenarios and 9 injection cases. Two scenarios
exercise structured model parsing with scripted local responses. All 45 pass.
The original master baseline had 3 failures in 43 cases.

The runner copies the displayed draft at the approval boundary. The scorer
compares every write to that snapshot, including customer, items, amounts,
notification text, action-specific operation ID and run. Each required
assertion affects the verdict. The fixture preserves receipts across retries
and records a committed effect even if its first response was lost.

Terminal outcomes skip pending ordinary resumes. Explicit replay cases still
exercise the checkpoint. An unexpected case exception fails that case and
the runner continues. The trace includes the approval snapshot and call history.

The tests deliberately corrupt passing traces to check detection of missing
writes, changed customer, operation suffix, price, channel and excess searches.
The generated report measures offline graph behavior. Hosted database,
authentication and live-model behavior require separate integration evidence.
