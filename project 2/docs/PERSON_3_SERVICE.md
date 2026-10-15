# Person 3 — Generation, citations, and API

## Ownership

Build the question-to-answer service and enforce grounded, article-level
citations.

## Tasks

- Define the request and response schemas.
- Implement the answer-generation prompt.
- Pass only retrieved passages to the generator.
- Require a citation for every legal claim.
- Implement explicit abstention when evidence is missing.
- Validate citations against returned chunk IDs and article metadata.
- Build the API and a minimal question interface.
- Record request, retrieval, generation, and end-to-end latency.
- Add tests for unsupported questions and fabricated citations.

## Dependencies

This work can start without another person's output by mocking retrieval
results with the agreed schema. It will need Person 2's retrieval interface
for end-to-end integration and Person 1's real article metadata for final
citation checks.

## Handoff

Provide:

- Local run command
- API endpoint and response example
- Prompt and model configuration
- Citation-validation behavior
- Abstention behavior
- API and citation tests
