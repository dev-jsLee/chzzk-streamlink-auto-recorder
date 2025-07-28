#!/bin/bash

echo "치지직 녹화기 Docker Compose 시작 (Nginx 포함)..."

# Nginx를 포함한 모든 서비스 시작
docker-compose --profile with-nginx up -d

echo "서비스가 시작되었습니다."
echo "웹 인터페이스: http://localhost (또는 https://localhost)"
echo "로그 확인: docker-compose logs -f callisto-web" 