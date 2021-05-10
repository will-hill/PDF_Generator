# Python image to use.
#FROM python:3.8

# Set the working directory to /app
#WORKDIR /app

# copy the font requirements file used for dependencies
#COPY requirements.txt Cursive.ttf .

# Install any needed packages specified in requirements.txt
#RUN pip install --trusted-host pypi.python.org -r requirements.txt

# Copy the rest of the working directory contents into the container at /app
#COPY pdf_writer_service.py .

# Run app.py when the container launches
#ENTRYPOINT ["python", "pdf_writer_service.py"]



# Python image to use.
FROM python:3.8

# Set the working directory to /app
WORKDIR /app

# copy the requirements file used for dependencies
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r requirements.txt

# Copy the rest of the working directory contents into the container at /app
COPY . .

# Run app.py when the container launches
ENTRYPOINT ["python", "app.py"]
