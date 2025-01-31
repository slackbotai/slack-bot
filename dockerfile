# Python 3.10.8 image as a base image
FROM python:3.10.8-slim

# Setting the working directory inside the container
WORKDIR /app

# Installing the necessary dependencies
## Copy requirements.in
COPY requirements.in .
## Install pip-tools and compile requirements
RUN pip install pip-tools
## Updates the dependencies on the requirements.txt file
RUN pip-compile requirements.in
## Running pip-sync to install the dependencies
RUN pip-sync
## Install Playwright and its dependencies
RUN python -m playwright install
RUN python -m playwright install-deps

# Copy the project source files to the container
COPY source/ /app/source/

# Setting environment variable for Python to run in optimised mode
ENV PYTHONUNBUFFERED=1

# Command to run the app
CMD ["python", "/app/source/main.py"]
