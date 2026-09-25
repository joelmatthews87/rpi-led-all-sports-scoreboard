FROM debian:trixie-slim

# Update and install dependencies.
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y \
        make \
        git \
        build-essential \
        python3 \
        python3-dev \
        python3-venv \
        cython3

# Copy only what the slow build steps below need. Application code is copied last so that
# editing a scene or data module doesn't invalidate the rpi-rgb-led-matrix compile.
WORKDIR /app
COPY /submodules ./submodules
COPY requirements.txt ./

# Created Python virtual environment. Update PATH and VIRTUAL_ENV environment variables to avoid needing to activate the virtual environment.
ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install required Python packages.
RUN pip install -r requirements.txt

# Build and install rpi-rgb-led-matrix Python package.
WORKDIR /app/submodules/rpi-rgb-led-matrix
RUN make build-python PYTHON=$(which python) && make install-python PYTHON=$(which python)

# Clean up cache and temp files.
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Return to main app folder and add the application code.
WORKDIR /app
COPY /setup ./setup
COPY /utils ./utils
COPY /data ./data
COPY /scenes ./scenes
COPY main.py ./

# Start app.
ENTRYPOINT ["python", "-u", "main.py"]
