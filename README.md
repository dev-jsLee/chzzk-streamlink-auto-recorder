# CHZZK 자동 녹화기 (DSM Linux 최적화)

Synology DSM Linux 환경에서 치지직(CHZZK) 라이브 스트림을 자동으로 녹화하는 프로그램입니다.

## 🚀 주요 특징

- **안정적인 녹화**: streamlink를 사용한 고품질 스트림 녹화
- **자동 재시도**: 네트워크 오류 시 자동 재시도 기능
- **우아한 종료**: 시그널 처리를 통한 안전한 종료
- **상세한 로깅**: 파일 및 콘솔 로깅 지원
- **프로세스 관리**: PID 기반 프로세스 관리
- **DSM 최적화**: Synology DSM 환경에 특화된 설정

## 📋 시스템 요구사항

### DSM 패키지 센터에서 설치 필요
- **Python 3.9+** (패키지 센터)
- **ffmpeg** (SynoCommunity 또는 패키지 센터)

### 추가 도구 (선택사항)
- **Git** (소스 코드 클론용)

## 🛠️ 설치 방법

### 1. 소스 코드 다운로드
```bash
# DSM SSH 접속 후
cd /volume1/docker  # 또는 원하는 위치
git clone <repository-url>
cd chzzk-streamlink-auto-recorder
```

### 2. 자동 설치 실행
```bash
chmod +x install.sh
./install.sh
```

### 3. 환경 설정
```bash
# .env 파일 편집
nano .env
```

다음 정보를 설정하세요:
```bash
# 필수 설정
CHANNEL_ID='치지직 채널 고유 ID'        # 채널 URL에서 추출
NID_AUT='NID_AUT 쿠키값'              # 브라우저 개발자 도구에서 확인
NID_SES='NID_SES 쿠키값'              # 브라우저 개발자 도구에서 확인

# 녹화 설정 (선택사항)
RECORD_DIR='/volume1/recordings/chzzk'  # 녹화 파일 저장 경로
CHECK_INTERVAL=60                       # 오프라인 체크 간격 (초)
RETRY_COUNT=3                          # 녹화 실패 시 재시도 횟수
```

## 🎯 사용 방법

### 기본 명령어
```bash
# 녹화 시작
./start.sh

# 녹화 중지
./stop.sh

# 상태 확인
./status.sh

# 실시간 로그 확인
tail -f chzzk_recorder.log
```

### 수동 실행 (디버깅용)
```bash
# 가상환경 활성화
source venv/bin/activate

# 직접 실행
python3 callisto.py
```

## 🔧 서비스 등록 (선택사항)

시스템 부팅 시 자동 시작하려면:

```bash
# systemd 서비스 등록
sudo systemctl enable chzzk-recorder
sudo systemctl start chzzk-recorder

# 서비스 상태 확인
sudo systemctl status chzzk-recorder
```

## 📁 디렉토리 구조

```
chzzk-streamlink-auto-recorder/
├── callisto.py          # 메인 녹화 프로그램
├── install.sh           # 설치 스크립트
├── start.sh            # 시작 스크립트
├── stop.sh             # 중지 스크립트
├── status.sh           # 상태 확인 스크립트
├── requirements.txt    # Python 의존성
├── default.env         # 환경설정 템플릿
├── .env               # 실제 환경설정 (사용자 생성)
├── venv/              # Python 가상환경
├── chzzk_recorder.log # 로그 파일
└── chzzk_recorder.pid # PID 파일
```

## 🚨 문제 해결

### 1. streamlink 설치 오류
```bash
# DSM에서 Python3 패키지가 설치되어 있는지 확인
python3 --version

# pip 업그레이드
pip3 install --upgrade pip
```

### 2. ffmpeg 없음 오류
- DSM 패키지 센터에서 "Video Station" 설치
- 또는 SynoCommunity에서 ffmpeg 설치

### 3. 권한 오류
```bash
# 스크립트 실행 권한 부여
chmod +x *.sh

# 녹화 디렉토리 권한 확인
ls -la /volume1/recordings/
```

### 4. 네트워크 연결 오류
- 방화벽 설정 확인
- DSM 네트워크 설정 점검
- 쿠키 값 재확인

## 📊 모니터링

### 로그 확인
```bash
# 실시간 로그
tail -f chzzk_recorder.log

# 최근 100줄
tail -n 100 chzzk_recorder.log

# 오류 로그만 필터링
grep ERROR chzzk_recorder.log
```

### 디스크 사용량 확인
```bash
# 녹화 디렉토리 용량
du -sh /volume1/recordings/chzzk

# 디스크 여유 공간
df -h /volume1
```

## ⚙️ 고급 설정

### 환경변수 상세 설정
```bash
# 로그 레벨 조정
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR

# 자동 삭제 설정 (일단위)
AUTO_DELETE_DAYS=30  # 30일 후 자동 삭제, 0=비활성화

# 디스크 사용률 제한
MAX_DISK_USAGE=80  # 80% 초과 시 경고
```

## 🔗 쿠키 값 확인 방법

1. 치지직 웹사이트 로그인
2. 브라우저 개발자 도구 (F12) 열기
3. Application/Storage 탭 → Cookies → https://chzzk.naver.com
4. `NID_AUT`와 `NID_SES` 값 복사

## 📞 지원

- 이슈 발생 시 `chzzk_recorder.log` 파일과 함께 문의
- 환경 정보: DSM 버전, Python 버전 포함

## 📝 업데이트 내역

### v2.0 (DSM 최적화)
- DSM Linux 환경 최적화
- 안정적인 오류 처리 추가
- 프로세스 관리 개선
- 상세한 로깅 시스템
- 자동 설치 스크립트 제공