# Random Fact API

![CI](https://github.com/Aqikop/random-fact-api/actions/workflows/ci.yml/badge.svg)

A small Flask API that returns random dog and cat facts. It's the first stage of a DevOps project: the app is containerized with Docker, and a GitHub Actions pipeline tests it, builds the image, and pushes it to Docker Hub on every push to `main`.

## Endpoints

| Route | Description |
|-------|-------------|
| `GET /health` | Health check, returns `{"status": "ok"}` |
| `GET /dog` | Random dog fact from a local dataset (`src/facts.json`) |
| `GET /dog/<id>` | Dog fact by index, or 404 if it doesn't exist |
| `GET /cat` | Random cat fact, fetched from [meowfacts](https://meowfacts.herokuapp.com/) (returns 502 if that service is down) |

Example:

```bash
curl localhost:5000/dog
# {"fact": "..."}
```

## Project structure

```
.
├── src/
│   ├── app.py            # Flask app
│   ├── facts.json        # Dog facts
│   └── test_app.py       # Unit tests
├── Dockerfile
├── requirements.txt      # Runtime dependencies (used in the image)
├── requirements-dev.txt  # Runtime + test dependencies
└── .github/workflows/ci.yml
```

## Run locally

Requires Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python src/app.py
```

The API is now at http://localhost:5000.

Run the tests:

```bash
pytest src/
```

The cat endpoint tests mock the external API, so the tests run without internet access.

## Run with Docker

Pull and run the published image:

```bash
docker run -p 5000:5000 aqikop/random-fact-api:latest
```

Or build it yourself:

```bash
docker build -t random-fact-api .
docker run -p 5000:5000 random-fact-api
```

The image is based on `python:3.12-slim`, installs only the runtime dependencies, runs as a non-root user, and serves the app with gunicorn.

## CI pipeline

The workflow in `.github/workflows/ci.yml` has two jobs:

1. **test**: runs on every push and pull request. It installs the dependencies and runs `pytest`.
2. **build-and-push**: runs only on pushes to `main`, and only if the tests pass. It logs in to Docker Hub using GitHub Secrets (`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`), builds the image, and pushes it with two tags:
   - `latest`
   - the commit SHA, so each image can be traced back to the commit that produced it

## Next steps

- Stage 2: push images to AWS ECR instead of Docker Hub
- Stage 3: deploy automatically to AWS (ECS or EC2)