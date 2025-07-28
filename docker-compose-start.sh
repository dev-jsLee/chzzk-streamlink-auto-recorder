#!/bin/bash

echo "치지직 녹화기 Docker Compose 시작..."

# 기본 서비스만 시작 (Nginx 없이)
docker-compose up -d callisto callisto-ffmpeg callisto-web

echo "서비스가 시작되었습니다."
echo "웹 인터페이스: http://localhost:5000"
echo "로그 확인: docker-compose logs -f callisto-web" 