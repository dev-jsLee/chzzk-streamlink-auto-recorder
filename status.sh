#!/bin/bash

# 치지직 자동 녹화기 상태 확인 스크립트

echo "=================================="
echo "치지직 자동 녹화기 상태 확인"
echo "=================================="

# PID 파일 확인
if [ -f "chzzk_recorder.pid" ]; then
    PID=$(cat chzzk_recorder.pid)
    
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ 상태: 실행 중"
        echo "📋 PID: $PID"
        
        # 프로세스 정보
        echo "⏰ 시작 시간: $(ps -o lstart= -p $PID)"
        echo "💾 메모리 사용량: $(ps -o rss= -p $PID | awk '{printf "%.1f MB", $1/1024}')"
        echo "🔄 CPU 사용률: $(ps -o %cpu= -p $PID)%"
        
        # 로그 파일 확인
        if [ -f "chzzk_recorder.log" ]; then
            echo ""
            echo "📝 최근 로그 (마지막 5줄):"
            echo "--------------------------------"
            tail -n 5 chzzk_recorder.log
        fi
        
        # 녹화 디렉토리 확인
        if [ -d "/volume1/recordings/chzzk" ]; then
            echo ""
            echo "📁 녹화 파일:"
            echo "--------------------------------"
            ls -lah /volume1/recordings/chzzk | tail -n 5
            
            # 디스크 사용량
            echo ""
            echo "💽 디스크 사용량:"
            df -h /volume1/recordings/chzzk | tail -n 1
        fi
        
    else
        echo "❌ 상태: 중지됨 (PID 파일은 존재하지만 프로세스 없음)"
        echo "🔧 PID 파일을 정리합니다..."
        rm -f chzzk_recorder.pid
    fi
else
    echo "❌ 상태: 중지됨"
fi

echo ""
echo "=================================="
echo "명령어:"
echo "시작: ./start.sh"
echo "중지: ./stop.sh"
echo "로그: tail -f chzzk_recorder.log"
echo "==================================" 