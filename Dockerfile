# Use an official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy dependency manifest and install required packages
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source
COPY main.py ./

# Set the default command to execute your script
ENTRYPOINT ["python", "main.py"]
