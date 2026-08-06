FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask
COPY portal.py .
ENV PORT=8080 PORTAL_DATA_DIR=/data
EXPOSE 8080
CMD ["python", "portal.py"]
