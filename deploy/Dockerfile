# The Google Ads MCP server over HTTP, for claude.ai.
#
# There is no pip install here, and that is the point: the server uses the
# Python standard library only. The image is the official Python base plus
# five scripts, so there is no dependency tree to audit and nothing to
# rebuild when a package publishes a security release.
FROM python:3.13-slim

# Run as a plain user. The process needs to read its configuration and
# append to its change log, nothing else.
RUN useradd --create-home --uid 10001 neo

WORKDIR /app
COPY --chown=neo:neo plugins/neo-google-ads/scripts/ /app/scripts/

# Credentials and the change log live here, mounted from the host so they
# survive a rebuild.
RUN mkdir -p /data && chown neo:neo /data
ENV GOOGLE_ADS_HOME=/data \
    GOOGLE_ADS_CONFIG=/data/config.json \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8

USER neo
EXPOSE 8788

# The health check asks the server itself, not the operating system: a
# process that is running but no longer answering is not healthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8788/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["python3", "/app/scripts/google-ads-http.py"]
CMD ["--host", "0.0.0.0", "--port", "8788", "--token-file", "/data/http-token"]
