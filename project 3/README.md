# The Specialist

CS496 AI Engineering · Fall 2026

The Specialist is an IT purchasing assistant. Describe a setup in your own words. The local Ollama model identifies the products and what needs to work together. The app researches live Tunisianet listings, displays retailer photos, and verifies the relevant specifications against source evidence. Shoppers can choose or refine a setup and open its product pages on Tunisianet.

The [November 16 enhanced brief](docs/monday-2026-11-16/README.md) is the project baseline. The [release guide](docs/person-4-release.md) records the checks and current limits.

## Run The Specialist

Run these commands from Project 3 with Python 3.12, Node.js, and Ollama installed.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci --prefix specialist/sandbox/sql
ollama pull ministral-3:8b
.\.venv\Scripts\python.exe -m specialist
```

Open the [shopping page](http://127.0.0.1:8767/shop/). The default uses live Tunisianet listings and a local model. Use `--catalog fixture` for repeatable tests with fictional listings. Shopping choices are saved locally for the browser session, and purchases take place on the retailer’s website.

The coursework workbench remains accessible at [Test customer](http://127.0.0.1:8767/customer/) and [Reviewer](http://127.0.0.1:8767/admin/). The server prints separate passcodes for those routes. The workbench runs the exact-proposal approval, order recheck and sandbox receipt flow. `--sandbox supabase` selects the team's dedicated database for that flow using the ignored `.env` file. **Support tickets** in the reviewer view opens the secondary fixture-based ticket flow.

## Who owns what

| Owner | Main code | What to show |
| --- | --- | --- |
| Person 1 | [`specialist/workflow/`](specialist/workflow/) and [`specialist/support/`](specialist/support/) | Follow a request from the local planner through case revisions, exact approval, and receipt recovery. |
| Person 2 | [`specialist/catalog/`](specialist/catalog/) and [`specialist/sandbox/`](specialist/sandbox/) | Show how the researcher obtains exact listing evidence and how the database records an approved action once. |
| Person 3 | [`specialist/verification/`](specialist/verification/) and [`evaluation/`](evaluation/) | Show how evidence produces pass, fail, or unknown findings, then compare the evaluation modes. See the [threat model](docs/evaluation/threat-model.md). |
| Person 4 | [`specialist/workbench/`](specialist/workbench/) and [`specialist/observability.py`](specialist/observability.py) | Run the customer and reviewer flows, inspect the trace, and reproduce the release checks. |

[Shared contracts](specialist/contracts/) define plans, listings and findings. The [core handoff](docs/specialist-core.md) and [hybrid planning guide](docs/specialist-hybrid.md) explain how the pieces fit together. [Historical handoffs](docs/archive/) record the team's earlier implementation work.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix specialist/sandbox/sql
.\.venv\Scripts\python.exe -m evaluation.comparison
.\.venv\Scripts\python.exe -m evaluation.legacy.run
.\.venv\Scripts\python.exe -m evaluation.local_model
```

The last command uses Ollama. Evaluation output goes to `.specialist/evaluation/`. The [reference results](evaluation/reference/) preserve earlier measured runs. The [release guide](docs/person-4-release.md) covers the hosted setup, fixture resets and optional LangSmith tracing.
