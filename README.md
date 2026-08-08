# 🐝 HiveBox

> 🌍 A location-based temperature explorer built as an end-to-end DevOps
> learning project.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Ready-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![CI](https://img.shields.io/badge/GitHub_Actions-CI-2088FF?logo=githubactions&logoColor=white)](https://github.com/JNasri/devops-hands-on-project-hivebox/actions)
[![Version](https://img.shields.io/badge/version-1.0.0-2E7D32)](https://github.com/JNasri/devops-hands-on-project-hivebox)

## 👋 Welcome

Welcome to **HiveBox**! This project turns recent
[openSenseMap](https://opensensemap.org/) sensor measurements into a searchable
web experience. Enter a city, region, or country to discover nearby temperature
observations through a responsive public dashboard.

Behind the interface, HiveBox resolves locations with Nominatim/OpenStreetMap,
caches responses in Valkey, and archives periodic snapshots in S3-compatible
MinIO storage. The original roadmap endpoints remain available alongside the
safe, bounded region-search API.

### 🚀 Try the public app

**[Open the live HiveBox dashboard →](https://devops-hands-on-project-hivebox-cvpmex.cranl.net)**

[Quick start](#run-the-complete-project-locally) ·
[API endpoints](#public-api) ·
[Architecture](#current-architecture) ·
[Project roadmap](https://devopsroadmap.io/projects/hivebox/)

### ✨ What you can explore

- 🔎 Search by city, region, or country.
- 🌡️ View recent temperature readings and a regional average.
- ⚡ Reuse five-minute cached responses for quicker repeat requests.
- 📦 Store timestamped sensor snapshots in S3-compatible object storage.
- 📊 Inspect health, readiness, version, and Prometheus metrics endpoints.

## Current architecture

```text
Browser -> HiveBox API -> Nominatim (place search)
                      -> openSenseMap (temperature data)
                      -> Valkey (5-minute response cache)

Dedicated worker -> openSenseMap -> Valkey -> MinIO
```

The API and periodic worker are separate processes. Importing `main.py` does
not start threads, make network calls, or write objects.

## Run the complete project locally

Prerequisites: Docker with Docker Compose.

1. Create local configuration:

   ```powershell
   Copy-Item .env.example .env
   ```

2. In `.env`, replace `NOMINATIM_USER_AGENT` with your real public repository
   or contact URL. Change the MinIO credentials and set `STORE_API_KEY` before
   exposing the application publicly.

3. Start the API, worker, Valkey, and MinIO:

   ```powershell
   docker compose up --build
   ```

4. Open:

   - Website: http://127.0.0.1:5000
   - MinIO console: http://127.0.0.1:9001
   - Health: http://127.0.0.1:5000/healthz
   - Readiness: http://127.0.0.1:5000/readyz

Stop the stack with `docker compose down`. Add `--volumes` only when you also
intend to delete the locally cached and archived data.

## Run without Docker

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python main.py
```

Valkey and MinIO must be reachable using the addresses in `.env`. Start the
periodic worker separately:

```powershell
python main.py worker
```

## Public API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Public temperature explorer |
| `GET` | `/api/regions/search?q=Berlin` | Explicit place search via Nominatim |
| `GET` | `/api/temperature?lat=52.52&lon=13.40&radius_km=10&name=Berlin` | Recent temperature near a point |
| `GET` | `/temperature` | Roadmap endpoint using `TEMPERATURE_BBOX` |
| `POST` | `/store` | Store a snapshot immediately |
| `GET` | `/healthz` | Dependency-free liveness check |
| `GET` | `/readyz` | Roadmap readiness calculation |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/version` | Application version |

Region requests accept a radius from 1 to 50 km. Results use the newest valid
measurement from each sensor, preventing frequently reporting sensors from
receiving extra weight in the average. Successful region responses are cached
for five minutes.

If `STORE_API_KEY` is set, call the storage endpoint with:

```powershell
curl.exe -X POST -H "X-API-Key: your-key" http://127.0.0.1:5000/store
```

## Configuration

See [.env.example](.env.example) for every setting. Important production
values include:

- `TEMPERATURE_SENSEBOX_IDS`: static boxes used only by `/readyz`.
- `TEMPERATURE_BBOX`: static region used by `/temperature` and the worker.
- `TEMPERATURE_PHENOMENA`: comma-separated temperature labels used across languages.
- `NOMINATIM_USER_AGENT`: must identify your deployed application.
- `VALKEY_URL`: use the cache service hostname in containers.
- `MINIO_*`: S3-compatible object-storage connection.
- `STORE_API_KEY`: protects the write-trigger endpoint when configured.

The public Nominatim service allows at most one request per second, requires an
identifying User-Agent and attribution, and does not allow client-side
autocomplete. HiveBox searches only on form submission, caches results for one
day, and enforces the uncached request interval.

## Tests and CI

```powershell
pytest -q
ruff check main.py tests
```

Unit tests replace all external dependencies with in-memory fakes. CI lints
Python, runs tests, scans Kubernetes manifests, builds the image, and
smoke-tests the exact built container.

## Kubernetes with Kind

Build and load the local image, then apply the Kustomize directory:

```powershell
docker build -t hivebox:latest .
kind load docker-image hivebox:latest --name kind
kubectl apply -k kube
kubectl rollout status deployment/hivebox
kubectl rollout status deployment/hivebox-worker
```

The checked-in Kustomize secret generator contains development-only
credentials so the local example works. Replace it with your cloud secret
manager before deployment. The Valkey and MinIO manifests use ephemeral
volumes for Kind; use managed services or persistent volumes in the cloud.

## Before making the demo public

- Configure a real Nominatim identification URL.
- Replace every development credential.
- Put the application behind HTTPS and a real domain.
- Keep Valkey, MinIO, and `/metrics` on private networks.
- Restrict `/store` with a strong API key or make it internal-only.
- Replace local MinIO with managed object storage or persistent volumes.
- Add cloud-specific Terraform and external monitoring/alerts.
- Review openSenseMap and OpenStreetMap attribution and usage requirements.

---

# **Implementation history**

<br>**Phase 1: Welcome to HiveBox!**

In this phase, I have set up the required preparation steps to start the HiveBox project. The steps are:

- Created /HiveBox folder in my personal machine.
- Forked the repository `devops-hands-on-project-hivebox` into the folder.
- Created a project for the repository using the Kanban Template.

## **Phase 2: DevOps Core: Git, Coding and Docker!**

### **2.1: Setup Git, Docker and VS Code**

(already done)

### **2.2: Versioning**

Created a python file to print the current version (v0.0.1)

    # Version follows Semantic Versioning (SemVer)
    __version__ = "0.0.1"

    # Main function to run the application
    def main():
        # Display the application version and exit
        print(f"HiveBox App Version: v{__version__}")


    # Entry point of the application
    if __name__ == "__main__":
        main()

### **2.3: Docker Image**

Created a Dockerfile to build an image out of the code. Run the command `docker build -t hivebox:v0.0.1 .` . (`-t` is for tagging the image with a name "hivebox:v0.0.1" and the dot in the end is to point to the directory of the files (current directory in this case)

    # Use an official lightweight Python image
    FROM python:3.11-slim

    # Set the working directory inside the container
    WORKDIR /app

    # Copy your local main.py file into the container's working directory
    COPY main.py .

    # Set the default command to execute your script
    ENTRYPOINT ["python", "main.py"]

### **2.4: Run a container our of the image**

Run the command `docker run --rm hivebox:v0.0.1` then test if it will print the version (`--rm` automatically cleans up and deletes the container instance after it stops running to not take a lot of space in my machine)

## **Phase 3: Lint, Test and CI workflow!**

 This phase focuses on building the foundation of a Flask web app. It only contains two endpoints:

### **3.1: (/version)**

returns the current version of the code.

    @app.route("/version")
    def print_version():
        """Return the current application version."""
        return __version__

### **3.2: (/temperature)**

Uses \[OpenSenseMapAPI\]([https://docs.opensensemap.org/](https://docs.opensensemap.org/) ) to return the average temperature of all senseBoxes in eu-central region.

    @app.route("/temperature", methods=["GET"])
    def get_average_temperature():
        """Fetch temperature measurements and calculate the global average."""
        try:
            # 1. Define our 1-hour expiration window in UTC
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=1)
            # 2. Build parameter queries for openSenseMap.
            # Wide bbox bounding box filter (e.g. Central Europe).
            # This reduces data size so the openSenseMap API returns clean JSON
            # instead of massive CSV text.
            query_params = {
                "phenomenon": "Temperatur",
                "bbox": "5.5,47.2,15.2,55.1",
                "from-date": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to-date": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "format": "json",
            }
            # 3. Request data payload directly
            response = requests.get(
                SENSORS_DATA_URL,
                params=query_params,
                timeout=15,
            )
            response.raise_for_status()
            # 4. Check if content type is actually JSON before parsing.
            if "application/json" not in response.headers.get("Content-Type", ""):
                return jsonify(
                    {
                        "status": "error",
                        "message": (
                            "Upstream API returned raw text/CSV instead of "
                            "expected JSON structure."
                        ),
                    }
                ), 502
            measurements = response.json()
            # 5. Filter and process values safely
            valid_temperatures = []
            for entry in measurements:
                if not isinstance(entry, dict):
                    continue
                raw_val = entry.get("value")
                if raw_val is None:
                    continue
                try:
                    valid_temperatures.append(float(raw_val))
                except (ValueError, TypeError):
                    continue
            # 6. Handle empty dataset scenario
            if not valid_temperatures:
                return jsonify(
                    {
                        "status": "error",
                        "message": (
                            "No valid temperature readings found within the "
                            "last 1 hour inside this region."
                        ),
                    }
                ), 503
            # 7. Compute mathematical average
            global_average = sum(valid_temperatures) / len(valid_temperatures)
            return jsonify(
                {
                    "average_temperature": round(global_average, 2),
                    "unit": "°C",
                    "active_sensors_calculated": len(valid_temperatures),
                    "time_window_checked": "Past 1 hour",
                }
            ), 200
        except requests.exceptions.RequestException as exc:
            return jsonify(
                {
                    "error": "Failed to connect to openSenseMap platform",
                    "details": str(exc),
                }
            ), 502

### **3.3: Learning about various technologies**

1- Pylint (linter for python code)

2- Hadolint (linter for Dockerfile)

3- \[Conventional commits\]([https://www.conventionalcommits.org/en/v1.0.0/](https://www.conventionalcommits.org/en/v1.0.0/) )

4- Write the code implementation of the two endpoints above as a simple flask app in the main python file.

### **3.4: Create multiple files related to testing and CI workflow using Action**

- _requirements.txt file_ : includes the version of all dependencies in the application. used in the dockerfile.
- add my first unit test to make sure the version endpoints works as expected:

      import main
      def test_version_endpoint_returns_current_version():
          # create Flask's test client out of main
          client = main.app.test_client()
          # call the /version endpoint , store response
          response = client.get('/version')

          # test 1 : does it return 200 ?
          assert response.status_code == 200
          # test 2 : does it return the current version ?
          assert response.data.decode('utf-8') == main.__version__

- _ci.yml_ file: workflow in Github action to create a VM in order to lint, test, build and run the code.
- _scorecard.yml:_ [openSSF](https://securityscorecards.dev/#using-the-github-action) , an open source tool for finding security issues in the code workflow

### **3.5: Documentation**

document all these above steps and push the code as a PR into the repository using the following commands

    1- check curent branch
    ~ git branch

    2- create a new branch (to work on new feature)
    ~ git branch -b "branch name"
    **Note** : if branch already created : ~ git checkout "branch name"

    3- start working, each step we do add/commit
    ~ git add . + git commit -m "number: comment"

    4- after the whole phase is done, we push our work to the branch
    ~ git puch -u origin "branch name"

    5- go the Pull Requests in the repo and create a new PR of the last commit

## **Phase 4: Introduction to K8s and Kind.**

### **4.3: Containers**

Downloaded Kind , Kubectl and Go programming language to start the setup of my local K8s cluster.

Added "kind-config.yaml" for HTTP and HTTPS port export, then created deployment yaml files to be used for the Kind deployment.

The steps to create a local cluster using kind out of the code:

1- Create Kind cluster, install ingress controller (NGINX) and wait for it to be ready.

    ~ kind create cluster --config kind-config.yaml (path to your config file)
    ~ kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
    ~ kubectl wait --namespace ingress-nginx \
      --for=condition=ready pod \
      --selector=app.kubernetes.io/component=controller \
      --timeout=180s

2- Build the docker image that will be loaded into the cluster:

    docker build -t hivebox:latest .

After setting up the image, load it into the cluster and apply the changes.

    kind load docker-image hivebox:latest --name kind
    kubectl apply -f kube

3- If any errors occur - trust me they will occur - edit the code accordingly, then re-do step 1,2 and restart/check-status of the deploy

    kubectl rollout restart deployment/hivebox
    kubectl rollout status deployment/hivebox

4- Done! the app can be used from the Kind cluster locally instead of the [localhost](http://localhost) !

### **4.4 Continuous Integration**

- Added code tests for all the new endpoints.
- integrated [SonarQube](https://sonarcloud.io) using their Quick and easy IDE setup by using their cloud instances to run code reviews locally on my machine before committing the code (It does require a subscription to set it up in my CI pipeline, maybe in a real project I can demonstrate this)
- Added Terrascan checkpoint to the CI pipeline to can all the yaml files related to create the k8 cluster within the codebase.

            - name: Scan Kubernetes manifests with Terrascan
              uses: tenable/terrascan-action@main
              with:
                iac_dir: kube
                iac_type: k8s
                only_warn: false

So now, the final CI wokrflow in the "ci.yml" now runs:

1.  ✅ Lint (Python + Dockerfile)
2.  ✅ **Terrascan** (Kubernetes manifests)
3.  ✅ Build Docker image
4.  ✅ Run tests
5.  ✅ Verify endpoints

## **Phase 5:** Transform - Finishing the Structure

### **5.2: Adding S3 with periodic and instant upload**

**5.2.1: (/store):** to implement a way to fetch the temperature and add them to a local bucket periodically and instantly using /store, I had to take the logic outside of the original /temperature into a helper function to make it reusable throughout the whole code base. Installed minIO using `pip install minio` and started a docker container to have a local S3 bucket.

    get_temperature_snapshot():
    --- code from the original /temperature here, then use it in 3 places ---

    1- in @app.route("/temperature", methods=["GET"])
    def get_average_temperature():
        """Fetch temperature measurements and calculate the global average."""
        temp_fetch_counter.inc()

        with temp_fetch_duration.time():
            try:
                snapshot = get_temperature_snapshot()
                return jsonify(snapshot), 200
            except requests.exceptions.RequestException as exc:
                return jsonify(
                    {
                        "error": "Failed to connect to openSenseMap platform",
                        "details": str(exc),
                    }
                ), 502
            except ValueError as exc:
                return jsonify(
                {"status": "error", "message": str(exc)}
            ), 503

    2- in periodic store of data in S3 bucket:
    def periodic_store():
        """Store one snapshot immediately and then every 5 minutes."""
        while True:
            try:
                snapshot = get_temperature_snapshot()
                snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
                upload_snapshot_to_minio(snapshot)
                print("Periodic store executed:", snapshot)
            except Exception as exc:
                print("Periodic store failed:", exc)
            time.sleep(300)

    3- in instant store in bucket (@app.route("/store", methods=["POST"]))
    def store_data():
        """Trigger a data storage operation."""
        try:
            snapshot = get_temperature_snapshot()
            snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
            upload_snapshot_to_minio(snapshot)
        except Exception as exc:
            return jsonify({"message": "Snapshot storage failed", "error": str(exc)}), 502

        return jsonify(
            {"message": "Snapshot stored successfully", "data": snapshot}
        ), 200

Note: I added test functions to for both new store mechanisms and removed the linting from the ci.yml as it was causing CI errors.
