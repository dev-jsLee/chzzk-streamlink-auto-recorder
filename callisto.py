import re
import requests
import time
import subprocess
import datetime
import logging
import os
import sys
import signal
import threading
from pathlib import Path
from dotenv import load_dotenv

# 환경 변수 로딩
load_dotenv()

# 로깅 설정
logger = logging.getLogger('chzzk_recorder')
logging.basicConfig(
    level=logging.INFO, 
    format="[%(asctime)s] [%(levelname)s] %(message)s", 
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('chzzk_recorder.log', encoding='utf-8')
    ]
)

# 환경 변수 설정
CHANNEL_ID = os.getenv('CHANNEL_ID')
NID_AUT = os.getenv('NID_AUT')
NID_SES = os.getenv('NID_SES')
RECORD_DIR = os.getenv('RECORD_DIR', '/volume1/recordings/chzzk')  # DSM 기본 경로
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))  # 오프라인 체크 간격 (초)
RETRY_COUNT = int(os.getenv('RETRY_COUNT', '3'))  # 녹화 실패 시 재시도 횟수

# API 설정
CHZZK_API = f'https://api.chzzk.naver.com/service/v3/channels/{CHANNEL_ID}/live-detail'

headers = {  
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# 파일명에서 특수문자 제거
special_chars_remover = re.compile(r'[\\/:*?"<>|]')

# 전역 변수
current_recording_process = None
shutdown_flag = False

def signal_handler(signum, frame):
    """시그널 핸들러 - 우아한 종료"""
    global shutdown_flag, current_recording_process
    logger.info("종료 신호를 받았습니다. 프로그램을 종료합니다...")
    shutdown_flag = True
    
    if current_recording_process:
        logger.info("진행 중인 녹화를 종료합니다...")
        try:
            current_recording_process.terminate()
            current_recording_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            current_recording_process.kill()
        except Exception as e:
            logger.error(f"녹화 프로세스 종료 중 오류: {e}")
    
    sys.exit(0)

def check_dependencies():
    """필수 의존성 확인"""
    try:
        # streamlink 설치 확인
        result = subprocess.run(['streamlink', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info(f"Streamlink 버전: {result.stdout.strip()}")
        else:
            logger.error("Streamlink가 설치되지 않았습니다.")
            return False
            
        # 녹화 디렉토리 생성
        Path(RECORD_DIR).mkdir(parents=True, exist_ok=True)
        logger.info(f"녹화 디렉토리: {RECORD_DIR}")
        
        # 환경 변수 확인
        if not all([CHANNEL_ID, NID_AUT, NID_SES]):
            logger.error("필수 환경 변수가 설정되지 않았습니다 (CHANNEL_ID, NID_AUT, NID_SES)")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"의존성 확인 중 오류: {e}")
        return False

def get_live_info():
    """라이브 상태 정보 가져오기"""
    try:
        response = requests.get(CHZZK_API, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        content = data.get('content')
        
        if content is None:
            logger.info("채널이 장기간 스트리밍하지 않았습니다.")
            return None, None, None
            
        status = content.get('status')
        title = content.get('liveTitle', 'Unknown Title')
        channel_name = content.get('channel', {}).get('channelName', 'UnknownChannel')
        
        return status, title, channel_name
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API 요청 실패: {e}")
        return None, None, None
    except Exception as e:
        logger.error(f"라이브 정보 가져오기 실패: {e}")
        return None, None, None

def run_streamlink(title, channel_name):
    """Streamlink를 사용하여 녹화 시작"""
    global current_recording_process
    
    try:
        # 파일명 생성
        cleaned_title = special_chars_remover.sub('', title.strip())
        current_time = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        file_name = f"{current_time}_{channel_name}_{cleaned_title}"
        output_file = os.path.join(RECORD_DIR, f"{file_name}.mp4")
        
        logger.info(f"녹화 시작: {output_file}")
        
        # Streamlink 명령어 구성
        cmd = [
            'streamlink',
            '--ffmpeg-copyts',
            '--progress', 'no',
            '--retry-streams', '3',
            '--retry-open', '3',
            f'https://chzzk.naver.com/live/{CHANNEL_ID}',
            'best',
            '--http-cookie', f'NID_AUT={NID_AUT}',
            '--http-cookie', f'NID_SES={NID_SES}',
            '--output', output_file
        ]
        
        # 비동기로 Streamlink 실행
        current_recording_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        logger.info(f"녹화 프로세스 시작됨 (PID: {current_recording_process.pid})")
        
        # 프로세스 완료 대기 (비차단)
        return current_recording_process
        
    except Exception as e:
        logger.error(f"Streamlink 실행 중 오류: {e}")
        current_recording_process = None
        return None

def monitor_recording(process, title):
    """녹화 프로세스 모니터링"""
    try:
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            logger.info(f"녹화 완료: {title}")
        else:
            logger.error(f"녹화 실패 (종료 코드: {process.returncode})")
            if stderr:
                logger.error(f"오류 메시지: {stderr}")
                
    except Exception as e:
        logger.error(f"녹화 모니터링 중 오류: {e}")
    finally:
        global current_recording_process
        current_recording_process = None

def check_stream():
    """스트림 상태 확인 및 녹화 관리"""
    retry_count = 0
    last_status = None
    
    while not shutdown_flag:
        try:
            status, title, channel_name = get_live_info()
            
            if status == 'OPEN':
                if last_status != 'OPEN':
                    logger.info(f"{channel_name}님의 방송이 시작되었습니다!")
                    logger.info(f"방송 제목: {title}")
                    logger.info(f"https://chzzk.naver.com/live/{CHANNEL_ID}")
                    
                    # 녹화 시작 (재시도 로직 포함)
                    for attempt in range(RETRY_COUNT):
                        recording_process = run_streamlink(title, channel_name)
                        
                        if recording_process:
                            # 별도 스레드에서 녹화 모니터링
                            monitor_thread = threading.Thread(
                                target=monitor_recording,
                                args=(recording_process, title)
                            )
                            monitor_thread.daemon = True
                            monitor_thread.start()
                            break
                        else:
                            logger.warning(f"녹화 시작 실패 (시도 {attempt + 1}/{RETRY_COUNT})")
                            if attempt < RETRY_COUNT - 1:
                                time.sleep(5)
                
                # 녹화 중 상태 확인
                if current_recording_process:
                    if current_recording_process.poll() is not None:
                        logger.warning("녹화 프로세스가 예기치 않게 종료되었습니다.")
                        current_recording_process = None
                        
                time.sleep(10)  # 온라인 상태일 때는 10초마다 확인
                
            else:
                if last_status == 'OPEN':
                    logger.info("방송이 종료되었습니다.")
                    
                    # 진행 중인 녹화가 있다면 대기
                    if current_recording_process:
                        logger.info("녹화 완료를 기다리는 중...")
                        current_recording_process.wait()
                        current_recording_process = None
                        
                logger.info(f"오프라인 상태 - {CHECK_INTERVAL}초 후 재확인")
                time.sleep(CHECK_INTERVAL)
                
            last_status = status
            retry_count = 0  # 성공 시 재시도 카운터 리셋
            
        except KeyboardInterrupt:
            logger.info("사용자에 의해 중단되었습니다.")
            break
            
        except Exception as e:
            retry_count += 1
            logger.error(f"예기치 않은 오류 발생 (재시도 {retry_count}): {e}")
            
            if retry_count >= 5:
                logger.error("연속 오류가 5회 발생했습니다. 프로그램을 종료합니다.")
                break
                
            time.sleep(30)  # 오류 발생 시 30초 대기

def main():
    """메인 함수"""
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 50)
    logger.info("치지직 자동 녹화기 시작")
    logger.info(f"채널 ID: {CHANNEL_ID}")
    logger.info(f"녹화 디렉토리: {RECORD_DIR}")
    logger.info("=" * 50)
    
    # 의존성 확인
    if not check_dependencies():
        logger.error("의존성 확인 실패. 프로그램을 종료합니다.")
        sys.exit(1)
    
    try:
        check_stream()
    except Exception as e:
        logger.error(f"메인 루프에서 치명적 오류 발생: {e}")
        sys.exit(1)
    finally:
        logger.info("프로그램이 종료되었습니다.")

if __name__ == "__main__":
    main()