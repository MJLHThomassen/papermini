# The image the Linux test jobs run in (.github/workflows/ci.yml): Python with the
# system libraries Qt needs, so the tests do not download them from the Ubuntu
# package mirror on every run.
#
#   docker build --build-arg PYTHON=3.12 -t papermini-ci:py3.12 .github/ci-image
#
# CI builds it for each tested Python version, tagged with a hash of this file, and
# pushes it to ghcr.io the first time a version of this file is used: change this
# file and the next CI run builds the new image.
ARG PYTHON=3.12
FROM python:${PYTHON}-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/MJLHThomassen/papermini"
LABEL org.opencontainers.image.description="papermini's CI: Python and Qt's system libraries"

# git: actions/checkout and setuptools-scm (the version comes from the tags);
# the rest: what PySide6 (offscreen), OpenCV and onnxruntime load; fonts for Qt's text
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git ca-certificates \
      libegl1 libgl1 libopengl0 libglib2.0-0 libfontconfig1 libfreetype6 \
      libxkbcommon0 libdbus-1-3 libgomp1 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONDONTWRITEBYTECODE=1
