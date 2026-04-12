# Contributing to DivergeX

First off, thank you for considering contributing to DivergeX! It's people like you who make this project a great tool for the racing community.

## Code of Conduct

By participating in this project, you are expected to uphold our [Code of Conduct](CODE_OF_CONDUCT.md).

## How Can I Contribute?

### Reporting Bugs
*   Check the [Issues](https://github.com/example/repo/issues) to see if the bug has already been reported.
*   If not, use the **Bug Report** template to provide as much detail as possible.

### Suggesting Enhancements
*   Open an [Issue](https://github.com/example/repo/issues) using the **Feature Request** template.

### Pull Requests
1.  Fork the repo and create your branch from `main`.
2.  If you've added code that should be tested, add tests.
3.  Ensure the test suite passes.
4.  Make sure your code lints (PEP 8 for Python, ESLint for React).
5.  Link the PR to the relevant issue.

## Style Guidelines

### Python (Backend)
- Follow **PEP 8**.
- Use descriptive variable names.
- Type hints are encouraged.

### TypeScript / React (Frontend)
- Use functional components and hooks.
- Follow the established **glassmorphism** design patterns.
- Ensure mobile responsiveness for all new UI components.

## Local Development Setup

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
# Set up virtualenv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-api.txt
python3 -m uvicorn src.api.main:app --reload
```

Thank you for your contributions!
