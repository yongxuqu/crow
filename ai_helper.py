
import os
import streamlit as st
import requests
import json

class DoubaoAI:
    def __init__(self, api_key=None, model_id=None):
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        
        if not self.api_key:
            try:
                self.api_key = st.secrets["doubao"]["api_key"]
            except:
                try:
                    self.api_key = st.secrets["DOUBAO_API_KEY"]
                except:
                    pass
        
        if not self.model_id:
            try:
                self.model_id = st.secrets["doubao"]["model_id"]
            except:
                try:
                    self.model_id = st.secrets["DOUBAO_MODEL_ID"]
                except:
                    pass

    def generate_summary(self, text_content, context_type="general"):
        if not self.api_key:
            yield "Error: API Key not configured."
            return

        system_prompt = f"""You are an intelligent analyst assistant. 
        Your task is to summarize the following {context_type} data.
        Provide a concise, high-level summary of the key trends, interesting points, and anomalies.
        Use bullet points for clarity. Language: Chinese (Simplified).
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the data:\n\n{text_content}"}
        ]
        
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0.7,
            "stream": True
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            with requests.post(self.base_url, headers=headers, json=payload, stream=True, timeout=180) as response:
                if response.status_code != 200:
                    yield f"API Error {response.status_code}: {response.text}"
                    return

                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                json_data = json.loads(data_str)
                                content = json_data['choices'][0]['delta'].get('content', '')
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            yield f"Request Error: {str(e)}"

    def chat(self, messages):
        """
        Continue the conversation. Returns a generator for streaming.
        """
        if not self.api_key:
            yield "Error: API Key not configured."
            return

        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0.7,
            "stream": True
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            with requests.post(self.base_url, headers=headers, json=payload, stream=True, timeout=180) as response:
                if response.status_code != 200:
                    yield f"API Error {response.status_code}: {response.text}"
                    return

                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                content = data['choices'][0]['delta'].get('content', '')
                                if content:
                                    yield content
                            except:
                                pass
        except Exception as e:
            yield f"Stream Error: {str(e)}"

    def batch_translate(self, texts):
        """
        批量翻译文本列表 (English -> Chinese)
        Returns: list of translated strings
        """
        if not self.api_key or not texts:
            return texts
            
        # 简单处理：将文本列表合并为一个 prompt 发送，然后解析返回结果
        # 为了稳定性，我们使用 JSON 格式交互
        
        system_prompt = """You are a professional translator. 
        Translate the following list of texts from English to Chinese (Simplified).
        Maintain the original meaning, tone, and formatting.
        Return ONLY a valid JSON array of strings.
        Example Input: ["Hello", "World"]
        Example Output: ["你好", "世界"]
        """
        
        user_content = json.dumps(texts, ensure_ascii=False)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0.3, # 低温度以保证格式稳定
            "stream": False
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                res_json = response.json()
                content = res_json['choices'][0]['message']['content']
                # 尝试解析 JSON
                # 有时候模型会返回 markdown code block，需要处理
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                translated_texts = json.loads(content)
                if isinstance(translated_texts, list) and len(translated_texts) == len(texts):
                    return translated_texts
                else:
                    print("Translation returned invalid format or length mismatch.")
                    return texts # Fallback
            else:
                print(f"Translation API Error: {response.status_code}")
                return texts
        except Exception as e:
            print(f"Translation Exception: {e}")
            return texts

def get_doubao_client(api_key=None, model_id=None):
    return DoubaoAI(api_key, model_id)
