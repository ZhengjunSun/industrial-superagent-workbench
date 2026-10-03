FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV AGENT_DATABASE=/data/superagent.db
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "superagent.api:app", "--host", "0.0.0.0", "--port", "8000"]
