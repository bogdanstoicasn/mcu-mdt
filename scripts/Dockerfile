FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    # Python runtime
    python3 \
    python3-pip \
    python3-serial \
    python3-yaml \
    python3-pytest \
    python3-pytest-cov \
    # Build essentials
    make \
    build-essential \
    git \
    # AVR toolchain
    gcc-avr \
    binutils-avr \
    avr-libc \
    avrdude \
    # STM32 / ARM toolchain
    gcc-arm-none-eabi \
    binutils-arm-none-eabi \
    stlink-tools \
    && rm -rf /var/lib/apt/lists/*

# ruff is not in apt
RUN pip3 install --break-system-packages ruff

WORKDIR /workspace

COPY .. /workspace

CMD ["/bin/bash"]