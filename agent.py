from vllm import LLM, SamplingParams
from file import TOOLS, search_file, read_file, write_file
import json

# 1. vllm 모델 로드 (예시: Llama-3-8bstruct)
# GPU 가 있다면 GPU, 없으면 CPU 로 변경 가능
llm = LLM(model="meta-llama/Meta-Llama-3-8Bstruct", tensor_parallel_size=1)

# 2. 도구 실행 맵핑
FUNCTION_MAP = {
    "search_file": search_file,
   read_file": read_file,
    "write_file": write_file
}

# 3. 대화 루프
def run_agent():
    messages = []
    
 while True:
        user_input = input("\n[사용자]: ")
        if user_input == "exit":
            break
        
        # 사용자 메시지 추가
       .append({"role": "user", "content": user_input})
        
        # vllm 에게 툴 사용 가능하도록 설정
        sampling_params = SamplingParamstemperature=0.7, max_tokens=1024)
        
        # vllm 의 Tool Use 기능 활용 (최신 vllm 버전 지원 필요)        # tools 파라미터를 통해 모델에게 도구 정의 전달
        output = llm.chat(messages, sampling_params=sampling_params, tools=TOOLS)
        
        # 응답
        for item in output:
            content = item.outputs[0].text
            tool_calls = item.outputs[0].tool_calls # vllm >= 05.0 이상 지원
            
            # 도구 호출 감지
            if tool_calls:
                print(f"[모델]: 도구를 호출합니다. ({len(tool_calls)})")
                
                tool_results = []
                
                for tc in tool_calls:
                    tool_name = tc.function.name
                    args = json.loads(tc.function.arguments)
                    # 실제 도구 실행
                    if tool_name in FUNCTION_MAP:
                        result = FUNCTION_MAP[tool_name](**args)
                        tool_results.append({
                            "tool_call_id": tc.id,
                            "role": "tool",
                            "name": tool_name,
                            "content": result
                        })
                       (f"[도구 실행]: {tool_name} -> {result[:50]}...")
                    else:
                        tool_results.append({
                            "tool_call": tc.id,
                            "role": "tool",
                            "name": tool_name,
                            "content": "지원하지 않는 도구입니다."
                        })                
                # 실행 결과를 모델에게 다시 전달 (Context 추가)
                messages.append({"role": "assistant", "content": content}) # 모델의 도구 호출 이전
                messages.extend(tool_results)
                
                # 결과를 바탕으로 2 차 추론 (Model 답변 생성)
                final_output = llm.chat(messages, sampling_paramsampling_params, tools=TOOLS)
                
                # 최종 답변 출력
                for final_item in final_output:
                    final_content = final_item.outputs[0].text
 print(f"[모델]: {final_content}")
                    # 최종 메시지를 메시지에 추가하여 다음 대화 유지
                    messages.append({"role": "assistant", "content": final_content
                    break
            else:
                # 도구 호출이 없으면 바로 출력
                print(f"[모델]: {content}")
                messages.append({"role": "", "content": content})

if __name__ == "__main__":
    run_agent()

