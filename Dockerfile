FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown app:app /app/data
COPY --chown=app:app sales_agent ./sales_agent
COPY --chown=app:app static ./static
USER app
ENV HOST=0.0.0.0 DATA_DIR=/app/data PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health',timeout=3)" || exit 1
CMD ["python", "-m", "sales_agent"]
