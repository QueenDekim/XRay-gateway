ARG XRAY_IMAGE=ghcr.io/xtls/xray-core:26.10.21
FROM ${XRAY_IMAGE} AS xray
FROM python:3.13-alpine3.22
RUN apk add --no-cache nftables iproute2 ca-certificates curl
WORKDIR /app
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY gateway/ /app/
COPY scripts/render.py /app/render.py
CMD ["python3","-u","/app/main.py"]
