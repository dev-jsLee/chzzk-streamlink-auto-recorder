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
from typing import Optional, Tuple, Dict, Any


class ChzzkRecorder:
    """치지직 자동 녹화기 메인 클래스"""
    
    def __init__(self):
        """초기화"""
        # 환경 변수 로딩
        load_dotenv()
        
        # 로깅 설정
        self._setup_logging()
        
        # 환경 변수 설정
        self._load_environment_vars()
        
        # API 설정
        self._setup_api()
        
        # 상태 변수
        self.current_recording_process: Optional[subprocess.Popen] = None
        self.shutdown_flag: bool = False
        self.last_status: Optional[str] = None
        self.retry_count: int = 0
        
        # 파일명에서 특수문자 제거 정규식
        self.special_chars_remover = re.compile(r'[\\/:*?"<>|]')
        
        # 시그널 핸들러 등록
        self._setup_signal_handlers()
    
    def _setup_logging(self):
        """로깅 설정"""
        self.logger = logging.getLogger('chzzk_recorder')
        logging.basicConfig(
            level=logging.INFO, 
            format="[%(asctime)s] [%(levelname)s] %(message)s", 
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('chzzk_recorder.log', encoding='utf-8')
            ]
        )
    
    def _load_environment_vars(self):
        """환경 변수 로딩"""
        self.channel_id = os.getenv('CHANNEL_ID')
        self.nid_aut = os.getenv('NID_AUT')
        self.nid_ses = os.getenv('NID_SES')
        self.record_dir = os.getenv('RECORD_DIR', './recordings')
        self.check_interval = int(os.getenv('CHECK_INTERVAL', '60'))
        self.retry_count_max = int(os.getenv('RETRY_COUNT', '3'))
    
    def _setup_api(self):
        """API 설정"""
        self.chzzk_api = f'https://api.chzzk.naver.com/service/v3/channels/{self.channel_id}/live-detail'
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
    
    def _setup_signal_handlers(self):
        """시그널 핸들러 설정"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러 - 우아한 종료"""
        self.logger.info("종료 신호를 받았습니다. 프로그램을 종료합니다...")
        self.shutdown_flag = True
        
        if self.current_recording_process:
            self.logger.info("진행 중인 녹화를 종료합니다...")
            try:
                self.current_recording_process.terminate()
                self.current_recording_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.current_recording_process.kill()
            except Exception as e:
                self.logger.error(f"녹화 프로세스 종료 중 오류: {e}")
        
        sys.exit(0)
    
    def check_dependencies(self) -> bool:
        """필수 의존성 확인"""
        try:
            # streamlink 설치 확인
            result = subprocess.run(['streamlink', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.logger.info(f"Streamlink 버전: {result.stdout.strip()}")
            else:
                self.logger.error("Streamlink가 설치되지 않았습니다.")
                return False
                
            # 녹화 디렉토리 생성
            Path(self.record_dir).mkdir(parents=True, exist_ok=True)
            self.logger.info(f"녹화 디렉토리: {self.record_dir}")
            
            # 환경 변수 확인
            if not all([self.channel_id, self.nid_aut, self.nid_ses]):
                self.logger.error("필수 환경 변수가 설정되지 않았습니다 (CHANNEL_ID, NID_AUT, NID_SES)")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"의존성 확인 중 오류: {e}")
            return False
    
    def get_live_info(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """라이브 상태 정보 가져오기"""
        try:
            response = requests.get(self.chzzk_api, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            content = data.get('content')
            
            if content is None:
                self.logger.info("채널이 장기간 스트리밍하지 않았습니다.")
                return None, None, None
                
            status = content.get('status')
            title = content.get('liveTitle', 'Unknown Title')
            channel_name = content.get('channel', {}).get('channelName', 'UnknownChannel')
            
            return status, title, channel_name
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API 요청 실패: {e}")
            return None, None, None
        except Exception as e:
            self.logger.error(f"라이브 정보 가져오기 실패: {e}")
            return None, None, None
    
    def run_streamlink(self, title: str, channel_name: str) -> Optional[subprocess.Popen]:
        """Streamlink를 사용하여 녹화 시작"""
        try:
            # 파일명 생성
            cleaned_title = self.special_chars_remover.sub('', title.strip())
            current_time = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
            file_name = f"{current_time}_{channel_name}_{cleaned_title}"
            output_file = os.path.join(self.record_dir, f"{file_name}.mp4")
            
            self.logger.info(f"녹화 시작: {output_file}")
            
            # Streamlink 명령어 구성
            cmd = [
                'streamlink',
                '--ffmpeg-copyts',
                '--progress', 'no',
                '--retry-streams', '3',
                '--retry-open', '3',
                f'https://chzzk.naver.com/live/{self.channel_id}',
                'best',
                '--http-cookie', f'NID_AUT={self.nid_aut}',
                '--http-cookie', f'NID_SES={self.nid_ses}',
                '--output', output_file
            ]
            
            # 비동기로 Streamlink 실행
            self.current_recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.logger.info(f"녹화 프로세스 시작됨 (PID: {self.current_recording_process.pid})")
            
            return self.current_recording_process
            
        except Exception as e:
            self.logger.error(f"Streamlink 실행 중 오류: {e}")
            self.current_recording_process = None
            return None
    
    def monitor_recording(self, process: subprocess.Popen, title: str):
        """녹화 프로세스 모니터링"""
        try:
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.logger.info(f"녹화 완료: {title}")
            else:
                self.logger.error(f"녹화 실패 (종료 코드: {process.returncode})")
                if stderr:
                    self.logger.error(f"오류 메시지: {stderr}")
                    
        except Exception as e:
            self.logger.error(f"녹화 모니터링 중 오류: {e}")
        finally:
            self.current_recording_process = None
    
    def handle_live_start(self, title: str, channel_name: str):
        """라이브 시작 처리"""
        self.logger.info(f"{channel_name}님의 방송이 시작되었습니다!")
        self.logger.info(f"방송 제목: {title}")
        self.logger.info(f"https://chzzk.naver.com/live/{self.channel_id}")
        
        # 녹화 시작 (재시도 로직 포함)
        for attempt in range(self.retry_count_max):
            recording_process = self.run_streamlink(title, channel_name)
            
            if recording_process:
                # 별도 스레드에서 녹화 모니터링
                monitor_thread = threading.Thread(
                    target=self.monitor_recording,
                    args=(recording_process, title)
                )
                monitor_thread.daemon = True
                monitor_thread.start()
                break
            else:
                self.logger.warning(f"녹화 시작 실패 (시도 {attempt + 1}/{self.retry_count_max})")
                if attempt < self.retry_count_max - 1:
                    time.sleep(5)
    
    def handle_live_end(self):
        """라이브 종료 처리"""
        self.logger.info("방송이 종료되었습니다.")
        
        # 진행 중인 녹화가 있다면 대기
        if self.current_recording_process:
            self.logger.info("녹화 완료를 기다리는 중...")
            self.current_recording_process.wait()
            self.current_recording_process = None
    
    def check_recording_status(self):
        """녹화 상태 확인"""
        if self.current_recording_process:
            if self.current_recording_process.poll() is not None:
                self.logger.warning("녹화 프로세스가 예기치 않게 종료되었습니다.")
                self.current_recording_process = None
    
    def check_stream(self):
        """스트림 상태 확인 및 녹화 관리"""
        self.retry_count = 0
        
        while not self.shutdown_flag:
            try:
                status, title, channel_name = self.get_live_info()
                
                if status == 'OPEN':
                    if self.last_status != 'OPEN':
                        self.handle_live_start(title, channel_name)
                    
                    # 녹화 중 상태 확인
                    self.check_recording_status()
                    time.sleep(10)  # 온라인 상태일 때는 10초마다 확인
                    
                else:
                    if self.last_status == 'OPEN':
                        self.handle_live_end()
                        
                    self.logger.info(f"오프라인 상태 - {self.check_interval}초 후 재확인")
                    time.sleep(self.check_interval)
                    
                self.last_status = status
                self.retry_count = 0  # 성공 시 재시도 카운터 리셋
                
            except KeyboardInterrupt:
                self.logger.info("사용자에 의해 중단되었습니다.")
                break
                
            except Exception as e:
                self.retry_count += 1
                self.logger.error(f"예기치 않은 오류 발생 (재시도 {self.retry_count}): {e}")
                
                if self.retry_count >= 5:
                    self.logger.error("연속 오류가 5회 발생했습니다. 프로그램을 종료합니다.")
                    break
                    
                time.sleep(30)  # 오류 발생 시 30초 대기
    
    def start(self):
        """녹화기 시작"""
        self.logger.info("=" * 50)
        self.logger.info("치지직 자동 녹화기 시작")
        self.logger.info(f"채널 ID: {self.channel_id}")
        self.logger.info(f"녹화 디렉토리: {self.record_dir}")
        self.logger.info("=" * 50)
        
        # 의존성 확인
        if not self.check_dependencies():
            self.logger.error("의존성 확인 실패. 프로그램을 종료합니다.")
            sys.exit(1)
        
        try:
            self.check_stream()
        except Exception as e:
            self.logger.error(f"메인 루프에서 치명적 오류 발생: {e}")
            sys.exit(1)
        finally:
            self.logger.info("프로그램이 종료되었습니다.")


def main():
    """메인 함수"""
    recorder = ChzzkRecorder()
    recorder.start()


if __name__ == "__main__":
    main()