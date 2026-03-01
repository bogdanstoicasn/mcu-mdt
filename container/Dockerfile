FROM ubuntu:24.04

# No interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Base image setup
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    make \
    gcc \
    build-essential \
    git \
    avr-libc \
    gcc-avr \
    && rm -rf /var/lib/apt/lists/*

# Working directory setup
WORKDIR /workspace

# Copy project into container
COPY .. /workspace

# Install Python dependencies if pyproject exists
RUN pip3 install --upgrade pip

# Optional: install your project as editable
# RUN pip3 install -e pc_tool

CMD ["/bin/bash"]