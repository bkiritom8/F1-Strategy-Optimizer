FROM --platform=linux/amd64 nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Python 3.10
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3-pip \
    python3.10-distutils \
    curl \
    git \
    gcc \
    g++ \
    libhdf5-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 the default python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 \
    && python -m pip install --upgrade pip

WORKDIR /app

# Install ML dependencies first (cached layer)
COPY docker/requirements-ml.txt /tmp/requirements-ml.txt
RUN pip install --no-cache-dir -r /tmp/requirements-ml.txt

# Copy ML code
COPY ml/ /app/ml/
COPY src/ /app/src/

# NVIDIA env vars required for GPU access inside containers
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Python path
ENV PYTHONPATH="/app"

# No CMD — entry point is set per Vertex AI CustomJob definition
# (e.g. python -m ml.models.strategy_predictor --mode train ...)
