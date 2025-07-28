#!/bin/bash

echo "Docker Compose 설정 중..."

# 실행 권한 부여
chmod +x docker-compose-start.sh
chmod +x docker-compose-start-nginx.sh
chmod +x docker-compose-stop.sh
chmod +x docker-compose-restart.sh

# SSL 디렉토리 생성 (선택사항)
mkdir -p ssl

echo "Docker Compose 설정 완료!"
echo ""
echo "사용법:"
echo "  기본 시작: ./docker-compose-start.sh"
echo "  Nginx 포함: ./docker-compose-start-nginx.sh"
echo "  중지: ./docker-compose-stop.sh"
echo "  재시작: ./docker-compose-restart.sh" 