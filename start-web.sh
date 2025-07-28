#!/bin/bash

# 웹 서버 모드로 치지직 녹화기 시작
echo "치지직 녹화기 웹 서버를 시작합니다..."

# 가상환경 활성화
sh venv/bin/activate

# 웹 서버 모드로 실행
python3 hosting.py --web 