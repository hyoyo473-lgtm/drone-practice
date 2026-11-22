FROM python:3.12-slim
WORKDIR /app
COPY server.py .
COPY static ./static
ENV PORT=8080 DATA_DIR=/data TZ=Asia/Taipei
VOLUME ["/data"]
EXPOSE 8080
CMD ["python", "-u", "server.py"]
