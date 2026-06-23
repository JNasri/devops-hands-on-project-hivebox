# Use an official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy your local main.py file into the container's working directory
COPY main.py .

# Set the default command to execute your script
ENTRYPOINT ["python", "main.py"]
