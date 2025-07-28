#!/bin/bash

# 치지직 자동 녹화기 중지 스크립트

echo "치지직 자동 녹화기를 중지합니다..."

# PID 파일 확인
if [ ! -f "chzzk_recorder.pid" ]; then
    echo "❌ PID 파일이 없습니다. 녹화기가 실행되지 않았거나 이미 중지되었습니다."
    exit 1
fi

PID=$(cat chzzk_recorder.pid)

# 프로세스 확인
if ! ps -p $PID > /dev/null 2>&1; then
    echo "❌ 해당 PID($PID)의 프로세스가 존재하지 않습니다."
    rm -f chzzk_recorder.pid
    exit 1
fi

echo "녹화기 프로세스 중지 중... (PID: $PID)"

# SIGTERM 전송
kill $PID

# 최대 10초 대기
for i in {1..10}; do
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ 녹화기가 정상적으로 종료되었습니다."
        rm -f chzzk_recorder.pid
        exit 0
    fi
    echo "대기 중... ($i/10)"
    sleep 1
done

# 강제 종료
echo "⚠️  정상 종료되지 않아 강제 종료합니다..."
kill -9 $PID

# 확인
if ! ps -p $PID > /dev/null 2>&1; then
    echo "✅ 녹화기가 강제 종료되었습니다."
    rm -f chzzk_recorder.pid
else
    echo "❌ 프로세스 종료에 실패했습니다. 수동으로 확인해주세요."
    exit 1
fi 