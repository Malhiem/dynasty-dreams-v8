# Dynasty Dreams API image for the local E2E stack.
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
ARG E2E_MODE=false
RUN if [ "$E2E_MODE" = "true" ]; then \
      grep -v '^emergentintegrations==' requirements.txt > e2e-requirements.txt && \
      pip install --no-cache-dir -r e2e-requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY backend/ ./
RUN mkdir -p /app/memory

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
