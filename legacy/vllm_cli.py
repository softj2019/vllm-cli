import sys
import json
import http.client
import argparse
from typing import List, Optional

# === 설정 ===
VLLM_HOST = "localhost"
VLLM_PORT = 8100
API_PATH = "/v1/chat/completions"

# 초기 채팅 히스토리 (시스템 프롬프트 포함 가능)
CHAT_HISTORY: List[dict] = [
    {"role": "system", "content": "You are a helpful AI assistant."}
]

class VLLMClient:
    def __init__(self, host: str, port: int, model: str):
        self.host = host
        self.port = port
        self.model = model
        self.messages = CHAT_HISTORY.copy() # 세션 시작 시 히스토리 복사

    def send_message(self, user_message: str, temperature: float = 0.7) -> str:
        """
        vLLM API 에 POST 요청을 보내고 스트리밍 응답을 처리합니다.
        """
        # 사용자의 메시지를 메시지에 추가
        self.messages.append({"role": "user", "content": user_message})

        # 요청 바디 구성
        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": 4096, # 필요 시 수정
            "top_p": 0.9
        }

        conn = http.client.HTTPConnection(self.host, self.port, timeout=600)
        
        try:
            headers = {
                "Content-Type": "application/json; charset=utf8",            
                "Authorization": "Bearer empty", # vLLM 로컬 환경에서는 보통 토큰 불필요
                "Accept": "text/event-stream"
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

            conn.request("POST", API_PATH, body=body, headers=headers)
            response = conn.getresponse()

            if response.status != 200:
                error_body = response.read().decode('utf-8')
                conn.close()
                raise Exception(f"API Error {response.status}: {error_body}")

            # SSE 스트리밍 파싱 (http.client 사용 시 fp 활용)
            print("AI: ", end="", flush=True)
            content_buffer = ""
            is_done = False

            while True:
                chunk = response.fp.read(8192) # 8KB chunks 읽음
                if not chunk:
                    break
                
                text = chunk.decode('utf-8')
                lines = text.split('\n')
                
                # 각 줄 처리
                for line in lines:
                    if not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        is_done = True
                        break
                    
                    # 데이터 부분 추출 (data: {"..."} 에서 { ...} 추출)
                    data_str = line[6:]
                    if not data_str:
                        continue
                    
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices and "delta" in choices[0]:
                            delta_content = choices[0]["delta"].get("content", "")
                            print(delta_content, end="", flush=True)
                            content_buffer += delta_content
                            
                            # 실시간 스트리밍 동안 사용자의 내용을 히스토리에 저장하지 않고,
                            # 최종 응답이 완료된 후에야 메모리에 추가하는 전략을 사용합니다.
                    except json.JSONDecodeError:
                        continue
                
                if is_done:
                    break
            
            print() # 줄바꿈
            conn.close()

            # 완료된 응답을 히스토리에 추가 (다음 대화를 위해)
            self.messages.append({"role": "assistant", "content": content_buffer})
            return content_buffer

        except KeyboardInterrupt:
            print("\n[중단됨]")
            conn.close()
            raise
        except Exception as e:
            print(f"\n[에러 발생]: {e}")
            conn.close()
            raise

def clear_history():
    """대화 이력을 초기화합니다."""
    global CHAT_HISTORY
    CHAT_HISTORY = [
        {"role": "system", "content": "You are a helpful AI assistant."}
    ]
    print("대화 이력이 초기화되었습니다.")

def main():
    parser = argparse.ArgumentParser(description="vLLM Local Chat CLI (Stream)")
    parser.add_argument("-m", "--model", type=str, default="prov", 
                        help="사용할 모델명 (vLLM 에서 실행 중인 모델 이름)")
    parser.add_argument("-c", "--clear", action="store_true", help="대화 이력 초기화")
    
    args = parser.parse_args()

    if args.clear:
        clear_history()
        sys.exit(0)

    print(f"vLLM CLI 시작 (모델: {args.model}, 포트: {VLLM_PORT})")
    print("입력: 채팅 메시지 (Ctrl+C 또는 /q 로 종료)\n")

    client = VLLMClient(VLLM_HOST, VLLM_PORT, args.model)
    running = True

    while running:
        try:
            user_input = input("User > ").strip()
            
            if user_input == "/q" or user_input == "/quit":
                print("종료합니다.")
                break
            elif user_input == "/clear":
                clear_history()
                continue
            elif not user_input:
                continue

            try:
                client.send_message(user_input)
            except Exception as e:
                print(f"[처리 중 에러]: {e}")
        
        except EOFError:
            print("\n종료합니다.")
            running = False

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n프로세스가 강제 종료되었습니다.")
        sys.exit(1)
