[![Dynamic DevOps Roadmap](https://img.shields.io/badge/Dynamic_DevOps_Roadmap-559e11?style=for-the-badge&logo=Vercel&logoColor=white)](https://devopsroadmap.io/getting-started/)
[![Community](https://img.shields.io/badge/Join_Community-%23FF6719?style=for-the-badge&logo=substack&logoColor=white)](https://newsletter.devopsroadmap.io/subscribe)
[![Telegram Group](https://img.shields.io/badge/Telegram_Group-%232ca5e0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/DevOpsHive/985)
[![Fork on GitHub](https://img.shields.io/badge/Fork_On_GitHub-%2336465D?style=for-the-badge&logo=github&logoColor=white)](https://github.com/DevOpsHiveHQ/devops-hands-on-project-hivebox/fork)

# HiveBox - DevOps End-to-End Hands-On Project

<p align="center">
  <a href="https://devopsroadmap.io/projects/hivebox" style="display: block; padding: .5em 0; text-align: center;">
    <img alt="HiveBox - DevOps End-to-End Hands-On Project" border="0" width="90%" src="https://devopsroadmap.io/img/projects/hivebox-devops-end-to-end-project.png" />
  </a>
</p>

> [!CAUTION]
> **[Fork](https://github.com/DevOpsHiveHQ/devops-hands-on-project-hivebox/fork)** this repo, and create PRs in your fork, **NOT** in this repo!

> [!TIP]
> If you are looking for the full roadmap, including this project, go back to the [getting started](https://devopsroadmap.io/getting-started) page.

This repository is the starting point for [HiveBox](https://devopsroadmap.io/projects/hivebox/), the end-to-end hands-on project.

You can fork this repository and start implementing the [HiveBox](https://devopsroadmap.io/projects/hivebox/) project. HiveBox project follows the same Dynamic MVP-style mindset used in the [roadmap](https://devopsroadmap.io/).

The project aims to cover the whole Software Development Life Cycle (SDLC). That means each phase will cover all aspects of DevOps, such as planning, coding, containers, testing, continuous integration, continuous delivery, infrastructure, etc.

Happy DevOpsing ♾️

## Before you start

Here is a pre-start checklist:

- ⭐ <a target="_blank" href="https://github.com/DevOpsHiveHQ/dynamic-devops-roadmap">Star the **roadmap** repo</a> on GitHub for better visibility.
- ✉️ <a target="_blank" href="https://newsletter.devopsroadmap.io/subscribe">Join the community</a> for the project community activities, which include mentorship, job posting, online meetings, workshops, career tips and tricks, and more.
- 🌐 <a target="_blank" href="https://t.me/DevOpsHive/985">Join the Telegram group</a> for interactive communication.

## Preparation

- [Create GitHub account](https://docs.github.com/en/get-started/start-your-journey/creating-an-account-on-github) (if you don't have one), then [fork this repository](https://github.com/DevOpsHiveHQ/devops-hands-on-project-hivebox/fork) and start from there.
- [Create GitHub project board](https://docs.github.com/en/issues/planning-and-tracking-with-projects/creating-projects/creating-a-project) for this repository (use `Kanban` template).
- Each phase should be presented as a pull request against the `main` branch. Don’t push directly to the main branch!
- Document as you go. Always assume that someone else will read your project at any phase.
- You can get senseBox IDs by checking the [openSenseMap](https://opensensemap.org/) website. Use 3 senseBox IDs close to each other (you can use the following [5eba5fbad46fb8001b799786](https://opensensemap.org/explore/5eba5fbad46fb8001b799786), [5c21ff8f919bf8001adf2488](https://opensensemap.org/explore/5c21ff8f919bf8001adf2488), and [5ade1acf223bd80019a1011c](https://opensensemap.org/explore/5ade1acf223bd80019a1011c)). Just copy the IDs, you will need them in the next steps.

<br/>
<p align="center">
  <a href="https://devopsroadmap.io/projects/hivebox/" imageanchor="1">
    <img src="https://img.shields.io/badge/Get_Started_Now-559e11?style=for-the-badge&logo=Vercel&logoColor=white" />
  </a><br/>
</p>

---

# **Implementation**
 

## **Phase 1: Welcome to HiveBox!**
 
In this phase, I have set up the required preparation steps to start the HiveBox project. The steps are:
 

*   Created /HiveBox folder in my personal machine.
     
*   Forked the repository [devops-hands-on-project-hivebox](https://github.com/DevOpsHiveHQ/devops-hands-on-project-hivebox/fork) into the folder.
     
*   Created a project in GitHub for the repository using the Kanban Template.
     

## **Phase 2: DevOps Core: Git, Coding and Docker!**
 
This phase builds up the foundation of the project workflow.
 
**2.1:** Setup Git, Docker and VS Code (already done)
 
**2.2:** Created a python file to print the current version (v0.0.1)
 

    # Version follows Semantic Versioning (SemVer)
    __version__ = "0.0.1"
    
    # Main function to run the application
    def main():
        # Display the application version and exit
        print(f"HiveBox App Version: v{__version__}")
    
    
    # Entry point of the application
    if __name__ == "__main__":
        main()

**2.3:** Created a Dockerfile to build an image out of the code. Run the command `docker build -t hivebox:v0.0.1 .` . (`-t` is for tagging the image with a name "hivebox:v0.0.1" and the dot in the end is to point to the directory of the files (current directory in this case)
 

    # Use an official lightweight Python image
    FROM python:3.11-slim
    
    # Set the working directory inside the container
    WORKDIR /app
    
    # Copy your local main.py file into the container's working directory
    COPY main.py .
    
    # Set the default command to execute your script
    ENTRYPOINT ["python", "main.py"]

**2.4:** Run the command `docker run --rm hivebox:v0.0.1` to create a container out of the image and test if it will print the version (`--rm` automatically cleans up and deletes the container instance after it stops running to not take a lot of space in my machine)



## **Phase 3: Lint, Test and CI workflow!**
 
This phase focuses on building the foundation of a Flask web app. It only contains two endpoints:
1- (/version) : returns the current version of the code
2- (/temperature) : uses [OpenSenseMapAPI](https://docs.opensensemap.org/) to return the average temperature of all senseBoxes in eu-central region.
 
**3.1:** -> **3.3:** : Learning about various technologies, including:
1- Pylint (linter for python code)
2- Hadolint (linter for Dockerfile)
3- [Conventional commits](https://www.conventionalcommits.org/en/v1.0.0/)
4- Write the flask code in the main.py + add 2 endpoints with their code implementation:


 
**2.2:** Created a python file to print the current version (v0.0.1)