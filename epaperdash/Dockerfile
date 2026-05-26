FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ARG BUILD_ARCH
ARG BUILD_VERSION
LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="${BUILD_ARCH}"

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py renderer.py data.py ./
COPY templates ./templates

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "::", "--port", "8000"]
