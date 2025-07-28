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
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Tuple, Dict, Any
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit
import psutil


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
        self.recording_info: Dict[str, Any] = {}
        
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
            
            # 녹화 정보 업데이트
            self.recording_info = {
                'title': title,
                'channel_name': channel_name,
                'output_file': output_file,
                'start_time': datetime.datetime.now().isoformat(),
                'status': 'recording'
            }
            
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
                self.recording_info['status'] = 'completed'
                self.recording_info['end_time'] = datetime.datetime.now().isoformat()
            else:
                self.logger.error(f"녹화 실패 (종료 코드: {process.returncode})")
                self.recording_info['status'] = 'failed'
                self.recording_info['error'] = stderr
                if stderr:
                    self.logger.error(f"오류 메시지: {stderr}")
                    
        except Exception as e:
            self.logger.error(f"녹화 모니터링 중 오류: {e}")
            self.recording_info['status'] = 'error'
            self.recording_info['error'] = str(e)
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
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태 정보 반환"""
        status, title, channel_name = self.get_live_info()
        
        return {
            'live_status': status,
            'live_title': title,
            'channel_name': channel_name,
            'recording_status': self.recording_info.get('status', 'idle'),
            'recording_info': self.recording_info,
            'is_recording': self.current_recording_process is not None,
            'process_pid': self.current_recording_process.pid if self.current_recording_process else None,
            'last_status': self.last_status,
            'retry_count': self.retry_count,
            'shutdown_flag': self.shutdown_flag
        }
    
    def stop_recording(self):
        """녹화 중지"""
        if self.current_recording_process:
            self.logger.info("사용자 요청으로 녹화를 중지합니다...")
            try:
                self.current_recording_process.terminate()
                self.current_recording_process.wait(timeout=10)
                self.logger.info("녹화가 중지되었습니다.")
            except subprocess.TimeoutExpired:
                self.current_recording_process.kill()
                self.logger.info("녹화 프로세스를 강제 종료했습니다.")
            except Exception as e:
                self.logger.error(f"녹화 중지 중 오류: {e}")
            finally:
                self.current_recording_process = None
                self.recording_info['status'] = 'stopped'
                self.recording_info['end_time'] = datetime.datetime.now().isoformat()
    
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


# Flask 웹 서버 설정
app = Flask(__name__)
app.config['SECRET_KEY'] = 'chzzk-recorder-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 전역 녹화기 인스턴스
recorder = None
monitor_thread = None


def create_templates():
    """HTML 템플릿 생성"""
    templates_dir = Path('templates')
    templates_dir.mkdir(exist_ok=True)
    
    # 메인 HTML 템플릿
    html_template = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>치지직 자동 녹화기</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }
        .content {
            padding: 30px;
        }
        .status-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 25px;
            border-left: 5px solid #667eea;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
        }
        .status-online { background-color: #28a745; }
        .status-offline { background-color: #dc3545; }
        .status-recording { background-color: #ffc107; }
        .status-idle { background-color: #6c757d; }
        .control-buttons {
            display: flex;
            gap: 15px;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .btn-danger {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a52 100%);
            color: white;
        }
        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(255, 107, 107, 0.4);
        }
        .btn-secondary {
            background: #6c757d;
            color: white;
        }
        .btn-secondary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(108, 117, 125, 0.4);
        }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .info-item {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .info-item h3 {
            margin-top: 0;
            color: #667eea;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 10px;
        }
        .log-container {
            background: #1e1e1e;
            color: #00ff00;
            border-radius: 8px;
            padding: 20px;
            height: 300px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            margin-top: 20px;
        }
        .log-entry {
            margin-bottom: 5px;
            padding: 2px 0;
        }
        .log-time {
            color: #888;
        }
        .log-level-info { color: #00ff00; }
        .log-level-error { color: #ff4444; }
        .log-level-warning { color: #ffaa00; }
        .recording-info {
            background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }
        .recording-info h3 {
            color: #856404;
            margin-top: 0;
        }
        .file-list {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .file-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-bottom: 1px solid #eee;
        }
        .file-item:last-child {
            border-bottom: none;
        }
        .file-name {
            font-weight: 500;
        }
        .file-size {
            color: #666;
            font-size: 0.9em;
        }
        @media (max-width: 768px) {
            .control-buttons {
                flex-direction: column;
            }
            .btn {
                width: 100%;
            }
            .info-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎥 치지직 자동 녹화기</h1>
            <p>DSM 환경에서 치지직 라이브 스트림을 자동으로 녹화합니다</p>
        </div>
        
        <div class="content">
            <div class="status-card">
                <h2>
                    <span id="status-indicator" class="status-indicator status-idle"></span>
                    <span id="status-text">상태 확인 중...</span>
                </h2>
                <div class="control-buttons">
                    <button class="btn btn-primary" onclick="startMonitoring()">📡 모니터링 시작</button>
                    <button class="btn btn-danger" onclick="stopRecording()">⏹️ 녹화 중지</button>
                    <button class="btn btn-secondary" onclick="refreshStatus()">🔄 상태 새로고침</button>
                    <a href="/logs" class="btn btn-secondary" target="_blank">📋 로그 보기</a>
                    <a href="/files" class="btn btn-secondary" target="_blank">📁 녹화 파일</a>
                </div>
            </div>
            
            <div class="info-grid">
                <div class="info-item">
                    <h3>📺 라이브 상태</h3>
                    <p><strong>상태:</strong> <span id="live-status">확인 중...</span></p>
                    <p><strong>채널:</strong> <span id="channel-name">-</span></p>
                    <p><strong>제목:</strong> <span id="live-title">-</span></p>
                </div>
                
                <div class="info-item">
                    <h3>🎬 녹화 상태</h3>
                    <p><strong>상태:</strong> <span id="recording-status">확인 중...</span></p>
                    <p><strong>PID:</strong> <span id="process-pid">-</span></p>
                    <p><strong>시작 시간:</strong> <span id="start-time">-</span></p>
                </div>
                
                <div class="info-item">
                    <h3>⚙️ 시스템 정보</h3>
                    <p><strong>채널 ID:</strong> <span id="channel-id">-</span></p>
                    <p><strong>녹화 디렉토리:</strong> <span id="record-dir">-</span></p>
                    <p><strong>재시도 횟수:</strong> <span id="retry-count">-</span></p>
                </div>
            </div>
            
            <div id="recording-info" class="recording-info" style="display: none;">
                <h3>🎥 현재 녹화 정보</h3>
                <p><strong>제목:</strong> <span id="current-title">-</span></p>
                <p><strong>파일:</strong> <span id="current-file">-</span></p>
                <p><strong>시작 시간:</strong> <span id="current-start-time">-</span></p>
            </div>
            
            <div class="log-container" id="log-container">
                <div class="log-entry">
                    <span class="log-time">[시스템]</span>
                    <span class="log-level-info">웹 인터페이스가 시작되었습니다.</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const socket = io();
        let statusUpdateInterval;
        
        // 소켓 연결
        socket.on('connect', function() {
            console.log('웹소켓 연결됨');
            addLog('웹소켓 연결됨', 'info');
        });
        
        // 상태 업데이트 수신
        socket.on('status_update', function(data) {
            updateStatus(data);
        });
        
        // 로그 수신
        socket.on('log_update', function(data) {
            addLog(data.message, data.level);
        });
        
        function updateStatus(data) {
            // 상태 표시기 업데이트
            const indicator = document.getElementById('status-indicator');
            const statusText = document.getElementById('status-text');
            
            if (data.is_recording) {
                indicator.className = 'status-indicator status-recording';
                statusText.textContent = '녹화 중';
            } else if (data.live_status === 'OPEN') {
                indicator.className = 'status-indicator status-online';
                statusText.textContent = '라이브 중 (녹화 대기)';
            } else {
                indicator.className = 'status-indicator status-offline';
                statusText.textContent = '오프라인';
            }
            
            // 라이브 정보 업데이트
            document.getElementById('live-status').textContent = data.live_status || '오프라인';
            document.getElementById('channel-name').textContent = data.channel_name || '-';
            document.getElementById('live-title').textContent = data.live_title || '-';
            
            // 녹화 정보 업데이트
            document.getElementById('recording-status').textContent = data.recording_status || '대기 중';
            document.getElementById('process-pid').textContent = data.process_pid || '-';
            document.getElementById('start-time').textContent = data.recording_info?.start_time ? 
                new Date(data.recording_info.start_time).toLocaleString() : '-';
            
            // 시스템 정보 업데이트
            document.getElementById('channel-id').textContent = data.channel_id || '-';
            document.getElementById('record-dir').textContent = data.record_dir || '-';
            document.getElementById('retry-count').textContent = data.retry_count || '0';
            
            // 녹화 정보 표시
            const recordingInfo = document.getElementById('recording-info');
            if (data.is_recording && data.recording_info) {
                recordingInfo.style.display = 'block';
                document.getElementById('current-title').textContent = data.recording_info.title || '-';
                document.getElementById('current-file').textContent = data.recording_info.output_file || '-';
                document.getElementById('current-start-time').textContent = 
                    new Date(data.recording_info.start_time).toLocaleString();
            } else {
                recordingInfo.style.display = 'none';
            }
        }
        
        function addLog(message, level = 'info') {
            const container = document.getElementById('log-container');
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            
            const time = new Date().toLocaleTimeString();
            const levelClass = `log-level-${level}`;
            
            entry.innerHTML = `
                <span class="log-time">[${time}]</span>
                <span class="${levelClass}">${message}</span>
            `;
            
            container.appendChild(entry);
            container.scrollTop = container.scrollHeight;
            
            // 로그 항목이 너무 많으면 오래된 것들 제거
            if (container.children.length > 100) {
                container.removeChild(container.firstChild);
            }
        }
        
        function startMonitoring() {
            fetch('/api/start', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        addLog('모니터링이 시작되었습니다.', 'info');
                    } else {
                        addLog('모니터링 시작 실패: ' + data.message, 'error');
                    }
                })
                .catch(error => {
                    addLog('요청 실패: ' + error.message, 'error');
                });
        }
        
        function stopRecording() {
            fetch('/api/stop', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        addLog('녹화가 중지되었습니다.', 'info');
                    } else {
                        addLog('녹화 중지 실패: ' + data.message, 'error');
                    }
                })
                .catch(error => {
                    addLog('요청 실패: ' + error.message, 'error');
                });
        }
        
        function refreshStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    updateStatus(data);
                    addLog('상태가 새로고침되었습니다.', 'info');
                })
                .catch(error => {
                    addLog('상태 새로고침 실패: ' + error.message, 'error');
                });
        }
        
        // 페이지 로드 시 상태 확인
        document.addEventListener('DOMContentLoaded', function() {
            refreshStatus();
            
            // 5초마다 상태 자동 업데이트
            statusUpdateInterval = setInterval(refreshStatus, 5000);
        });
        
        // 페이지 언로드 시 인터벌 정리
        window.addEventListener('beforeunload', function() {
            if (statusUpdateInterval) {
                clearInterval(statusUpdateInterval);
            }
        });
    </script>
</body>
</html>'''
    
    with open(templates_dir / 'index.html', 'w', encoding='utf-8') as f:
        f.write(html_template)


@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    """상태 정보 API"""
    global recorder
    if recorder:
        status = recorder.get_status()
        status.update({
            'channel_id': recorder.channel_id,
            'record_dir': recorder.record_dir
        })
        return jsonify(status)
    else:
        return jsonify({
            'live_status': 'unknown',
            'recording_status': 'not_initialized',
            'is_recording': False
        })


@app.route('/api/start', methods=['POST'])
def api_start():
    """모니터링 시작"""
    global recorder, monitor_thread
    
    if monitor_thread and monitor_thread.is_alive():
        return jsonify({'success': False, 'message': '이미 모니터링이 실행 중입니다.'})
    
    try:
        recorder = ChzzkRecorder()
        monitor_thread = threading.Thread(target=recorder.check_stream, daemon=True)
        monitor_thread.start()
        return jsonify({'success': True, 'message': '모니터링이 시작되었습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """녹화 중지"""
    global recorder
    
    if not recorder:
        return jsonify({'success': False, 'message': '녹화기가 초기화되지 않았습니다.'})
    
    try:
        recorder.stop_recording()
        return jsonify({'success': True, 'message': '녹화가 중지되었습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/logs')
def view_logs():
    """로그 파일 보기"""
    try:
        with open('chzzk_recorder.log', 'r', encoding='utf-8') as f:
            logs = f.read()
        return f'<pre style="background: #1e1e1e; color: #00ff00; padding: 20px; font-family: monospace;">{logs}</pre>'
    except FileNotFoundError:
        return '<p>로그 파일을 찾을 수 없습니다.</p>'


@app.route('/files')
def view_files():
    """녹화 파일 목록"""
    global recorder
    
    if not recorder:
        return '<p>녹화기가 초기화되지 않았습니다.</p>'
    
    try:
        record_dir = Path(recorder.record_dir)
        files = []
        
        for file_path in record_dir.glob('*.mp4'):
            stat = file_path.stat()
            files.append({
                'name': file_path.name,
                'size': stat.st_size,
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime),
                'path': str(file_path)
            })
        
        # 최신 파일부터 정렬
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>녹화 파일 목록</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .file-item { padding: 10px; border-bottom: 1px solid #eee; }
                .file-name { font-weight: bold; }
                .file-info { color: #666; font-size: 0.9em; }
            </style>
        </head>
        <body>
            <h1>📁 녹화 파일 목록</h1>
            <a href="/">← 메인으로 돌아가기</a>
        '''
        
        for file in files:
            size_mb = file['size'] / (1024 * 1024)
            html += f'''
            <div class="file-item">
                <div class="file-name">{file['name']}</div>
                <div class="file-info">
                    크기: {size_mb:.1f} MB | 
                    수정: {file['modified'].strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
            '''
        
        html += '</body></html>'
        return html
        
    except Exception as e:
        return f'<p>파일 목록을 불러오는 중 오류가 발생했습니다: {e}</p>'


def start_web_server():
    """웹 서버 시작"""
    global recorder
    
    # HTML 템플릿 생성
    create_templates()
    
    # 기본 녹화기 초기화
    recorder = ChzzkRecorder()
    
    print("=" * 60)
    print("�� 치지직 자동 녹화기 웹 인터페이스")
    print("=" * 60)
    print(f"📡 웹 서버가 시작되었습니다.")
    print(f"🌍 접속 주소: http://localhost:5000")
    print(f"�� 녹화 디렉토리: {recorder.record_dir}")
    print(f"📋 로그 파일: chzzk_recorder.log")
    print("=" * 60)
    print("�� 사용법:")
    print("1. 웹 브라우저에서 http://localhost:5000 접속")
    print("2. '모니터링 시작' 버튼으로 자동 녹화 시작")
    print("3. '녹화 중지' 버튼으로 현재 녹화 중지")
    print("4. '로그 보기'로 상세 로그 확인")
    print("5. '녹화 파일'로 저장된 파일 목록 확인")
    print("=" * 60)
    
    # Flask 서버 시작
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)


def main():
    """메인 함수"""
    if len(sys.argv) > 1 and sys.argv[1] == '--web':
        # 웹 서버 모드
        start_web_server()
    else:
        # 콘솔 모드 (기존 방식)
        recorder = ChzzkRecorder()
        recorder.start()


if __name__ == "__main__":
    main()