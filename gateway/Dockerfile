ARG XRAY_IMAGE=ghcr.io/xtls/xray-core:26.10.21
FROM ${XRAY_IMAGE} AS xray
FROM python:3.13-alpine3.22 AS metadata
WORKDIR /src
COPY . .
ARG SOURCE_REVISION
RUN python scripts/build_version.py --revision "$SOURCE_REVISION" --output /build-info.json
FROM python:3.13-alpine3.22
ARG XRAY_IMAGE
LABEL io.xray-gateway.core-image="$XRAY_IMAGE"
RUN apk add --no-cache nftables iproute2 ca-certificates curl
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt
WORKDIR /app
ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision="$SOURCE_REVISION" io.xray-gateway.update-protocol="1"
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY gateway/ /app/
COPY scripts/render.py /app/render.py
COPY VERSION /VERSION
COPY release-history.json /release-history.json
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/licenses/xray-gateway/
COPY --from=metadata /build-info.json /app/_build.json
CMD ["python3","-u","/app/main.py"]
