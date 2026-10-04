FROM ubuntu:22.04

LABEL maintainer="Industrial AI Architecture"
LABEL description="Hardened OpenPLC Runtime v3 container with Modbus/TCP, OPC UA, and Web UI"

ENV DEBIAN_FRONTEND=noninteractive

# Install core build dependencies for OpenPLC Runtime v3 (Ubuntu 22.04 provides Python 3.10+)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    sudo \
    curl \
    build-essential \
    pkg-config \
    bison \
    flex \
    autoconf \
    automake \
    libtool \
    make \
    python3 \
    python3-pip \
    python3-venv \
    sqlite3 \
    libsqlite3-dev \
    cmake \
    openssl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workdir

# Clone OpenPLC v3 directly into /workdir so relative paths (/workdir/webserver) match
RUN git clone https://github.com/thiagoralves/OpenPLC_v3.git .

# Patch credentials.py with __future__ annotations for robust typing compatibility across Python versions
RUN sed -i '1s/^/from __future__ import annotations\n/' /workdir/webserver/credentials.py

# Create persistent storage directory and execute installer
RUN mkdir -p /docker_persistent && \
    ./install.sh docker

# Populate factory-default configuration files and symlinks expected by start_openplc.sh
RUN touch /docker_persistent/mbconfig.cfg && \
    touch /docker_persistent/persistent.file && \
    mkdir -p /docker_persistent/st_files && \
    cp /workdir/webserver/openplc.db /docker_persistent/openplc.db && \
    cp /workdir/webserver/openplc.db /workdir/webserver/openplc_default.db && \
    cp /workdir/webserver/dnp3.cfg /docker_persistent/dnp3.cfg && \
    cp /workdir/webserver/dnp3.cfg /workdir/webserver/dnp3_default.cfg && \
    cp -r /workdir/webserver/st_files/. /docker_persistent/st_files/ && \
    cp -r /workdir/webserver/st_files/. /workdir/webserver/st_files_default/ && \
    cp /workdir/webserver/active_program /docker_persistent/active_program && \
    cp /workdir/webserver/active_program /workdir/webserver/active_program_default && \
    ln -sf /docker_persistent/mbconfig.cfg /workdir/webserver/mbconfig.cfg && \
    ln -sf /docker_persistent/persistent.file /workdir/webserver/persistent.file && \
    ln -sf /docker_persistent/openplc.db /workdir/webserver/openplc.db && \
    ln -sf /docker_persistent/dnp3.cfg /workdir/webserver/dnp3.cfg && \
    ln -sf /docker_persistent/st_files /workdir/webserver/st_files && \
    ln -sf /docker_persistent/active_program /workdir/webserver/active_program

VOLUME /docker_persistent

EXPOSE 502 8080 4840

ENTRYPOINT ["./start_openplc.sh"]
