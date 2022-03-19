FROM alpine:latest 

RUN apk add speedtest-cli

ENTRYPOINT speedtest --json
