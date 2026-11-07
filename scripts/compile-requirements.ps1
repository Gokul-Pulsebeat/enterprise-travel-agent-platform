# Run pip-compile inside the exact container environment used in CI and Cloud Run
docker run --rm `
  -v "${PWD}:/workspace" `
  -w /workspace `
  python:3.11-slim `
  bash -c "pip install --no-cache-dir pip-tools && pip-compile --resolver=backtracking requirements.in -o requirements.txt"