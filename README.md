# Random Fact API

![CI](https://github.com/Aqikop/random-fact-api/actions/workflows/ci.yml/badge.svg)

A small Flask API that returns random dog and cat facts. It's a staged DevOps project: the app is containerized with Docker, and a GitHub Actions pipeline tests it, builds the image, pushes it to both Docker Hub and AWS ECR, and deploys it to an AWS EC2 instance on every push to `main`.

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

## CI/CD pipeline

The workflow in `.github/workflows/ci.yml` has three jobs:

1. **test**: runs on every push and pull request. It installs the dependencies and runs `pytest`.
2. **build-and-push**: runs only on pushes to `main`, and only if the tests pass. It logs in to Docker Hub and AWS ECR, builds the image once, and pushes the same image to both registries with two tags each:
   - `latest`
   - the commit SHA, so each image can be traced back to the commit that produced it
3. **deploy**: runs only after `build-and-push` succeeds. It connects to the EC2 instance over SSH, pulls the image tagged with the exact commit SHA from ECR, replaces the running container, and then checks `GET /health` on the public address (6 attempts, 5 seconds apart). If the health check never returns 200, the job fails.

Credentials are stored as GitHub Secrets:

- Docker Hub: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`
- AWS (push to ECR): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
- Deployment: `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`

The AWS keys belong to a dedicated IAM user whose policy allows only pushing images to this one ECR repository, not the account owner's credentials. The SSH key is a separate key pair used only by the pipeline.

This is **continuous deployment**: every change that passes the tests and is merged to `main` goes live automatically, without a manual approval step.

## Deployment architecture

```
git push to main
      |
      v
GitHub Actions: test -> build-and-push -> deploy
                           |                 |
                           v                 | SSH (CI key)
              Docker Hub + AWS ECR           v
              (latest + commit SHA)     EC2 instance (Ubuntu, Docker)
                           |                 |
                           +---- pull -------+  (instance IAM role, ECR read-only)
                                             |
                                             v
                                   container on port 5000
                                             |
                                             v
                               health check: GET /health
```

- **Compute:** one small Ubuntu EC2 instance in `ap-southeast-1` running the app in Docker with `--restart unless-stopped`.
- **Image pulls:** the instance uses an IAM role with ECR pull-only permissions. No AWS keys are stored on the server.
- **Network:** the security group allows port 5000 (the app) and port 22 (SSH). GitHub-hosted runners have changing IP addresses, so SSH cannot be limited to a single address; access is protected by key-only authentication and a dedicated CI key.
- **Traceability:** the pipeline always deploys the commit SHA tag, never `latest`, so `docker ps` on the server shows which commit is live.

### Limitations

- The deploy replaces the container in place, so there is a few seconds of downtime between stopping the old container and starting the new one.
- The health check runs after the old container has been removed. If it fails, the job turns red but the broken version keeps running until the next good push or a manual rollback.
- If the instance itself fails, nothing replaces it.

An orchestrator such as ECS addresses these with rolling deployments and automatic task replacement, which is the planned next step.

### Manual rollback

SSH to the instance and run a previous commit SHA from ECR:

```bash
aws ecr get-login-password --region ap-southeast-1 | \
  docker login --username AWS --password-stdin \
  <account-id>.dkr.ecr.ap-southeast-1.amazonaws.com

docker rm -f random-fact-api
docker run -d --name random-fact-api --restart unless-stopped -p 5000:5000 \
  <account-id>.dkr.ecr.ap-southeast-1.amazonaws.com/random-fact-api:<previous-commit-sha>
```

### Operating the instance

- Stop the instance when it is not needed. A stopped instance still pays for its disk, so terminate it when finished with it.
- The public IP address changes whenever the instance is stopped and started. After a restart, update `EC2_HOST` in GitHub Secrets, or the deploy job will fail.
- A push to `main` while the instance is stopped makes the deploy job fail. Start the instance and re-run the job.

## Next steps

- Stage 3b: move the same deployment to ECS Fargate (task definition, service, rolling deploys)
- Stage 4 (optional): provision the infrastructure with Terraform
