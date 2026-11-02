ARG XRAY_IMAGE=ghcr.io/xtls/xray-core:26.10.21
FROM ${XRAY_IMAGE} AS xray
FROM python:3.13-alpine3.22 AS metadata
WORKDIR /src
COPY . .
ARG SOURCE_REVISION
RUN python scripts/build_version.py --revision "$SOURCE_REVISION" --output /build-info.json
FROM python:3.13-alpine3.22
RUN apk add --no-cache nftables iproute2 ca-certificates curl
WORKDIR /app
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY gateway/ /app/
COPY scripts/render.py /app/render.py
COPY VERSION /VERSION
COPY --from=metadata /build-info.json /app/_build.json
CMD ["python3","-u","/app/main.py"]
