#!/bin/bash

# DSM Linux용 치지직 자동 녹화기 설치 스크립트
set -e

echo "=================================="
echo "치지직 자동 녹화기 설치 시작"
echo "=================================="

# 가상환경 생성
echo "Python 가상환경 생성 중..."
python3 -m venv venv
sh venv/bin/activate

# pip 업그레이드
echo "pip 업그레이드 중..."
pip install --upgrade pip

# 의존성 설치
echo "의존성 패키지 설치 중..."
pip install -r requirements.txt

# 디렉토리 구조 생성
echo "디렉토리 구조 생성 중..."
mkdir -p /volume1/recordings/chzzk
mkdir -p logs

# 환경설정 파일 복사
if [ ! -f ".env" ]; then
    echo "환경설정 파일 생성 중..."
    cp default.env .env
    echo "⚠️  .env 파일을 편집하여 채널 정보와 쿠키를 설정해주세요!"
fi

# 실행 권한 부여
chmod +x callisto.py
chmod +x start.sh
chmod +x stop.sh

# systemd 서비스 파일 생성 (선택사항)
if [ -d "/etc/systemd/system" ]; then
    echo "systemd 서비스 파일 생성 중..."
    tee /etc/systemd/system/chzzk-recorder.service > /dev/null <<EOF
[Unit]
Description=CHZZK Auto Recorder
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python $(pwd)/callisto.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    echo "서비스 등록 완료. 다음 명령어로 시작할 수 있습니다:"
    echo "sudo systemctl enable chzzk-recorder"
    echo "sudo systemctl start chzzk-recorder"
fi

echo ""
echo "=================================="
echo "설치 완료!"
echo "=================================="
echo ""
echo "다음 단계:"
echo "1. .env 파일을 편집하여 채널 정보 설정"
echo "2. 녹화 시작: ./start.sh"
echo "3. 녹화 중지: ./stop.sh"
echo ""
echo "로그 확인: tail -f chzzk_recorder.log"
echo "" 