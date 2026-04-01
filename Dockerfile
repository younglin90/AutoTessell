FROM ubuntu:24.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev \
    curl ca-certificates git cmake build-essential \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# OpenFOAM 2406
RUN curl -fsSL https://dl.openfoam.com/add-debian-repo.sh | bash \
    && apt-get update \
    && apt-get install -y --no-install-recommends openfoam2406 \
    && rm -rf /var/lib/apt/lists/*

# MMG (mesh quality post-processing)
RUN git clone --depth 1 https://github.com/MmgTools/mmg.git /tmp/mmg \
    && mkdir /tmp/mmg/build && cd /tmp/mmg/build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
    && make -j$(nproc) && make install \
    && rm -rf /tmp/mmg

# Python dependencies
WORKDIR /app
COPY pyproject.toml .
RUN pip install --break-system-packages -e ".[dev,cad,netgen,volume,desktop]" 2>/dev/null || \
    pip install --break-system-packages \
    click rich pydantic structlog \
    trimesh meshio numpy pymeshfix pyacvd pyvista pymeshlab open3d \
    pytetwild netgen-mesher cadquery gmsh \
    fastapi "uvicorn[standard]" python-multipart websockets \
    pytest pytest-mock

# Copy project
COPY . .
RUN pip install --break-system-packages -e .

# OpenFOAM environment
ENV OPENFOAM_DIR=/usr/lib/openfoam/openfoam2406

# Expose desktop server port
EXPOSE 9720

# Default: run tests
CMD ["pytest", "tests/", "-v", "--tb=short"]
