#!/bin/bash

# 치지직 자동 녹화기 시작 스크립트

echo "치지직 자동 녹화기를 시작합니다..."

# 가상환경 활성화
if [ -d "venv" ]; then
    sh ./venv/bin/activate
    echo "가상환경 활성화됨"
else
    echo "⚠️  가상환경이 없습니다. install.sh를 먼저 실행해주세요."
    exit 1
fi

# 환경설정 확인
if [ ! -f ".env" ]; then
    echo "❌ .env 파일이 없습니다. default.env를 복사하여 설정해주세요."
    exit 1
fi

# PID 파일 확인
if [ -f "chzzk_recorder.pid" ]; then
    PID=$(cat chzzk_recorder.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  녹화기가 이미 실행 중입니다 (PID: $PID)"
        echo "중지하려면 ./stop.sh를 실행하세요."
        exit 1
    else
        echo "기존 PID 파일 삭제"
        rm -f chzzk_recorder.pid
    fi
fi

# 백그라운드에서 실행
echo "백그라운드에서 녹화기 시작..."
python3 callisto.py &
PID=$!

# PID 저장
echo $PID > chzzk_recorder.pid
echo "✅ 녹화기가 시작되었습니다 (PID: $PID)"
echo ""
echo "로그 확인: tail -f chzzk_recorder.log"
echo "중지: ./stop.sh"
echo "상태 확인: ./status.sh" 