FROM python:3.13-alpine3.22 AS metadata
WORKDIR /src
COPY . .
ARG SOURCE_REVISION
RUN python scripts/build_version.py --revision "$SOURCE_REVISION" --output /build-info.json
FROM python:3.13-alpine3.22
RUN apk add --no-cache docker-cli docker-cli-compose ca-certificates
WORKDIR /app
ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision="$SOURCE_REVISION" io.xray-gateway.update-protocol="1"
COPY updater/*.py /app/
COPY gateway/update_protocol.py gateway/version.py /app/
COPY VERSION /VERSION
COPY release-history.json /release-history.json
COPY --from=metadata /build-info.json /app/_build.json
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/licenses/xray-gateway/
CMD ["python3","-u","/app/agent.py"]
