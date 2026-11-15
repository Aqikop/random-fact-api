# Random Fact API

![CI](https://github.com/Aqikop/random-fact-api/actions/workflows/ci.yml/badge.svg)

A small Flask API that returns random dog and cat facts. It's a staged DevOps project: the app is containerized with Docker, and a GitHub Actions pipeline tests it, builds the image, and pushes it to both Docker Hub and AWS ECR on every push to `main`.

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

## Pull from AWS ECR

The image is also stored in a private AWS ECR repository (`ap-southeast-1`). Pulling requires AWS credentials with ECR read permissions. ECR login tokens are temporary (about 12 hours), so log in again when one expires:

```bash
aws ecr get-login-password --region ap-southeast-1 | \
  docker login --username AWS --password-stdin \
  <account-id>.dkr.ecr.ap-southeast-1.amazonaws.com

docker pull <account-id>.dkr.ecr.ap-southeast-1.amazonaws.com/random-fact-api:latest
docker run -p 5000:5000 <account-id>.dkr.ecr.ap-southeast-1.amazonaws.com/random-fact-api:latest
```

Replace `<account-id>` with the AWS account ID that owns the repository.

An ECR lifecycle policy keeps the repository small: untagged images expire after 1 day, and only the 10 most recent images are kept.

## CI pipeline

The workflow in `.github/workflows/ci.yml` has two jobs:

1. **test**: runs on every push and pull request. It installs the dependencies and runs `pytest`.
2. **build-and-push**: runs only on pushes to `main`, and only if the tests pass. It logs in to Docker Hub and AWS ECR, builds the image once, and pushes the same image to both registries with two tags each:
   - `latest`
   - the commit SHA, so each image can be traced back to the commit that produced it

Credentials are stored as GitHub Secrets:

- Docker Hub: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`
- AWS: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`

The AWS keys belong to a dedicated IAM user whose policy allows only pushing images to this one ECR repository, not the account owner's credentials.

## Next steps

- Stage 3: deploy automatically to AWS (ECS or EC2)
- Stage 4 (optional): provision the infrastructure with Terraform
