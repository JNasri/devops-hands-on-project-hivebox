Implementation


Phase 1: Welcome to HiveBox!

In this phase, I have set up the required preparation steps to start the HiveBox project. The steps are:

Created /HiveBox folder in my personal machine.

Forked the repository devops-hands-on-project-hivebox into the folder.

Created a project for the repository using the Kanban Template.

Phase 2: DevOps Core: Git, Coding and Docker!

This phase builds the foundation of the project workflow.

2.1: Setup Git, Docker and VS Code (already done)

2.2: Created a python file to print the current version (v0.0.1)

# Version follows Semantic Versioning (SemVer)
__version__ = "0.0.1"

# Main function to run the application
def main():
    # Display the application version and exit
    print(f"HiveBox App Version: v{__version__}")


# Entry point of the application
if __name__ == "__main__":
    main()

2.3: Created a Dockerfile to build an image out of the code. Run the command docker build -t hivebox:v0.0.1 . . (-t is for tagging the image with a name "hivebox:v0.0.1" and the dot in the end is to point to the directory of the files (current directory in this case)

# Use an official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy your local main.py file into the container's working directory
COPY main.py .

# Set the default command to execute your script
ENTRYPOINT ["python", "main.py"]

2.4: Run the command docker run --rm hivebox:v0.0.1 to create a container out of the image and test if it will print the version (--rm automatically cleans up and deletes the container instance after it stops running to not take a lot of space in my machine)

Phase 3: Lint, Test and CI workflow!

 This phase focuses on building the foundation of a Flask web app. It only contains two endpoints:

1- (/version) : returns the current version of the code.

@app.route("/version")
def print_version():
    """Return the current application version."""
    return __version__

2- (/temperature) : uses [OpenSenseMapAPI](https://docs.opensensemap.org/) to return the average temperature of all senseBoxes in eu-central region.

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

3.1: -> 3.3: Learning about various technologies

1- Pylint (linter for python code)

2- Hadolint (linter for Dockerfile)

3- [Conventional commits](https://www.conventionalcommits.org/en/v1.0.0/)

4- Write the code implementation of the two endpoints above as a simple flask app in the main python file.

3.4: Create multiple files related to testing and CI workflow using Action

requirements.txt file : includes the version of all dependencies in the application. used in the dockerfile.

add my first unit test to make sure the version endpoints works as expected:

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

ci.yml file: workflow in Github action to create a VM in order to lint, test, build and run the code.

scorecard.yml: openSSF , an open source tool for finding security issues in the code workflow

3.5: document all these above steps and push the code as a PR into the repository using the following commands:

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

Phase 4: Introduction to K8s and Kind. 

4.3 Containers: Downloaded Kind , Kubectl and Go programming language to start the setup of my local K8s cluster.

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

4- Done! the app can be used from the Kind cluster locally instead of the localhost!

4.4 Continuous Integration:

Added code tests for all the new endpoints.

integrated SonarQube using their Quick and easy IDE setup by using their cloud instances to run code reviews locally on my machine before committing the code (It does require a subscription to set it up in my CI pipeline, maybe in a real project I can demonstrate this).

Added Terrascan checkpoint to the CI pipeline to can all the yaml files related to create the k8 cluster within the codebase.

      - name: Scan Kubernetes manifests with Terrascan
        uses: tenable/terrascan-action@main
        with:
          iac_dir: kube
          iac_type: k8s
          only_warn: false

So now, the final CI wokrflow in the "ci.yml" now runs:
✅ Lint (Python + Dockerfile)
✅ Terrascan (Kubernetes manifests) ← NEW
✅ Build Docker image
✅ Run tests
✅ Verify endpoints

