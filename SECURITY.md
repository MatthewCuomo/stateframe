# Security Policy

`stateframe` is a local-first exploratory data analysis library. The deterministic
scan engine and interactive viewer are designed to work without sending dataset
contents to external services.

## Reporting A Vulnerability

Please report suspected security issues privately to the project maintainer
instead of opening a public issue first.

Until a dedicated security contact is published, use the maintainer's GitHub
profile at:

https://github.com/MatthewCuomo

## Data Handling Expectations

- Do not add private datasets, credentials, tokens, or notebook outputs with
  sensitive rows to the repository.
- Keep large local datasets out of Git and out of release distributions.
- Treat examples and tests as public unless explicitly documented otherwise.
