FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements-hosted.txt ./
RUN pip install --no-cache-dir -r requirements-hosted.txt && groupadd -g 10001 rebirth && useradd -u 10001 -g rebirth -M rebirth
COPY rebirth ./rebirth
COPY dist ./dist
COPY examples ./examples
COPY knowledge ./knowledge
COPY config/contracts.json config/hosted-no-cloud.json ./config/
COPY agentarts/prompts ./agentarts/prompts
COPY design-preview/dist ./design-preview/dist
COPY deploy ./deploy
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python", "deploy/healthcheck.py"]
CMD ["python", "deploy/platform.py"]
