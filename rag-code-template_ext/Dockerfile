FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY rag-code-template_ext/requirements-e.txt /tmp/requirements-rag.txt
COPY pipeline/requirements.txt /tmp/requirements-pipeline.txt
RUN pip install --no-cache-dir -r /tmp/requirements-rag.txt -r /tmp/requirements-pipeline.txt
COPY rag-code-template_ext/ /app/rag-code-template_ext/
COPY pipeline/ /app/pipeline/
COPY data/ /app/data/
WORKDIR /app/rag-code-template_ext
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "rag_external-web_pdf_closed_llm:app", "--host", "0.0.0.0", "--port", "8001"]
