# Random Fact API

![CI](https://github.com/Aqikop/random-fact-api/actions/workflows/ci.yml/badge.svg)

A small Flask API that returns random dog and cat facts. It's a staged DevOps project: the app is containerized with Docker, and a GitHub Actions pipeline tests it, builds the image, pushes it to both Docker Hub and AWS ECR, and deploys it to AWS ECS Fargate on every push to `main`.

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
├── ecs/
│   └── task-definition.json   # ECS task definition (the pipeline fills in the image)
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
3. **deploy**: runs only after `build-and-push` succeeds. It:
   - puts the commit SHA image from ECR into `ecs/task-definition.json`
   - registers it as a new task definition revision and updates the ECS service
   - waits until the rolling deployment is stable (the job fails if it is not)
   - looks up the new task's public IP and checks `GET /health` (6 attempts, 5 seconds apart)

Credentials are stored as GitHub Secrets:

- Docker Hub: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`
- AWS: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`

The AWS keys belong to a dedicated IAM user, not the account owner. Its permissions are limited to pushing images to this one ECR repository, updating this one ECS service, registering task definitions, and passing the task execution role to ECS only.

The cluster, service and container names are not secrets, so they are set as `env:` values in the `deploy` job.

This is **continuous deployment**: every change that passes the tests and is merged to `main` goes live automatically, without a manual approval step.

## Deployment architecture

```
git push to main
      |
      v
GitHub Actions: test -> build-and-push -> deploy
                           |                 |
                           v                 | register task definition
              Docker Hub + AWS ECR           | (image = commit SHA)
              (latest + commit SHA)          | update service, wait for stable
                           |                 v
                           |        ECS service (Fargate, rolling update)
                           |                 |
                           +---- pull -------+  (task execution role)
                                             |
                                             v
                                  task: container on port 5000
                                  logs -> CloudWatch (/ecs/random-fact-api)
                                             |
                                             v
                               health check: GET /health
```

- **Compute:** one ECS Fargate task (0.25 vCPU, 0.5 GB) in the default VPC in `ap-southeast-1`. The cluster is `random-fact-api-cluster` and the service is `random-fact-api-service`. There are no servers to manage.
- **Task definition:** stored in `ecs/task-definition.json` and versioned with the code. The image in the file is a placeholder; the pipeline replaces it with the commit SHA image on every deploy, so each task definition revision points at one commit.
- **Image pulls and logs:** the task execution role (`ecsTaskExecutionRole`) lets ECS pull from ECR and write logs to CloudWatch. The app itself calls no AWS APIs, so there is no task role.
- **Rolling deployment:** the service keeps 100% of its tasks healthy and allows up to 200%, so ECS starts the new task and waits for it to pass its health check before stopping the old one.
- **Automatic rollback:** the deployment circuit breaker is on with rollback. If a new task keeps failing its container health check, ECS stops retrying and returns the service to the last good revision.
- **Health checks:** the container has its own health check (a Python request to `/health`, because the slim image has no `curl`), and the pipeline runs a second check against the live task after the deploy.
- **Network:** the task runs in public subnets with a public IP, and its security group allows inbound TCP 5000. There is no SSH access.
- **Traceability:** the pipeline always deploys the commit SHA tag, never `latest`, so the running task's image shows which commit is live.

### Tested failure case

To check the rollback, I deployed a task definition whose container health check pointed at a path that returns 404. The unit tests still passed, so the pipeline reached `deploy`. ECS started the new task, it failed its container health checks and was stopped, and the circuit breaker returned the service to the previous revision. A fix, pushed afterwards, went green.

### Limitations

- **No load balancer.** The task's public IP changes on every deployment, so there is no stable address. An Application Load Balancer would give one, plus health checks based on real traffic.
- **Public subnets and a public IP**, with port 5000 open to the world. This avoids the cost of a NAT gateway, but it is not a production network setup.
- **One task.** If the Availability Zone has a problem, there is a gap until ECS places a new task.
- **Long-lived AWS access keys** are stored in GitHub Secrets. GitHub OIDC would remove the need for stored keys.

### Manual rollback

Each deploy registers a new task definition revision. To go back to an earlier one:

```bash
aws ecs list-task-definitions --family-prefix random-fact-api --region ap-southeast-1

aws ecs update-service \
  --cluster random-fact-api-cluster \
  --service random-fact-api-service \
  --task-definition random-fact-api:<revision> \
  --region ap-southeast-1

aws ecs wait services-stable \
  --cluster random-fact-api-cluster \
  --services random-fact-api-service \
  --region ap-southeast-1
```

The next push to `main` deploys the new commit again, so fix the problem in the code before pushing.

### Find the running task's public IP

```bash
TASK=$(aws ecs list-tasks --cluster random-fact-api-cluster --service-name random-fact-api-service \
  --desired-status RUNNING --region ap-southeast-1 --query "taskArns[0]" --output text)
ENI=$(aws ecs describe-tasks --cluster random-fact-api-cluster --tasks $TASK --region ap-southeast-1 \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text)
aws ec2 describe-network-interfaces --network-interface-ids $ENI --region ap-southeast-1 \
  --query "NetworkInterfaces[0].Association.PublicIp" --output text
```

Then open `http://<ip>:5000/health`.

### Cost and operating notes

- Fargate is billed per second while a task runs, and public IPv4 addresses are billed as well. When you are not using the service, set the desired count to 0:

  ```bash
  aws ecs update-service --cluster random-fact-api-cluster --service random-fact-api-service \
    --desired-count 0 --region ap-southeast-1
  ```

- Set it back to 1 **before** pushing to `main`. With no running task, the deploy job's health check has no address to test and fails.
- CloudWatch logs are kept for 7 days.

## Next steps

- Stage 4: provision the infrastructure (ECR, ECS cluster and service, IAM roles, networking) with Terraform
- Add an Application Load Balancer for a stable address
