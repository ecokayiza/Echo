from openai import OpenAI
from config import Config

###########################################
# We use deepseek API for main LLM services
API_KEY = Config.API_KEY
BASE_URL = Config.BASE_URL
MODEL = Config.MODEL
############################################


class ChatModel:
    def __init__(self, api_key=API_KEY, base_url=BASE_URL, model=MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate_response(self, messages):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return response.choices[0].message['content']
    

if __name__ == "__main__":
    chat_model = ChatModel()
    test_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"}
    ]
    response = chat_model.generate_response(test_messages)
    print("Response from model:", response)
