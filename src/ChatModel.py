from openai import AsyncOpenAI
import asyncio
from Config import Config
from typing import Optional, List, Dict, Any, AsyncIterator
from pydantic import BaseModel
from abc import ABC, abstractmethod
from Schema import RAGRecord, RAGMetadata, ExtraAttributes

###########################################
# We use deepseek API for main LLM services
# We use async client which is more suitable for web servers
API_KEY = Config.API_KEY
BASE_URL = Config.BASE_URL
MODEL = Config.MODEL
############################################

# === Message Model ===
class Message(BaseModel):
    role: str       # "system", "user", "assistant", "tool"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None

# === Response Model ===
class Response(BaseModel):
    content: str
    token_usage: Optional[Dict[str, Any]] = None
    raw_response: Any

# === Utility Function for Usage Conversion ===
def _usage_to_dict(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    # openai-python v1 returns a pydantic-like model for usage (e.g. CompletionUsage)
    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    to_dict = getattr(usage, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if hasattr(usage, "__dict__"):
        return dict(usage.__dict__)
    return {"usage": str(usage)}

############################################
# We need structured outputs and tool function calls for a RAG system
# We also need token usage tracking and callbacks tracking
############################################

# === Basic Chat Model Interface Definition ===
class BaseChatModel(ABC):
    def __init__(self, api_key=API_KEY, base_url=BASE_URL, model=MODEL, temperature=1.0):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature

    @abstractmethod
    async def generate_response(self, messages: List[Dict[str, str]],
                                tools:Optional[List[Dict]]=None,
                                stop:Optional[List[str]]=None,
                                callbacks:Optional[Any]=None,
                                **kwargs
                                ) -> Response:
        """Generate a response from the chat model given a list of messages."""
        pass
    
    @abstractmethod
    async def stream_response(self, messages: List[Dict[str, str]],
                                tools:Optional[List[Dict]]=None,
                                stop:Optional[List[str]]=None,
                                callbacks:Optional[Any]=None,
                                **kwargs
                              ) -> AsyncIterator[str]:
        """Stream a response from the chat model given a list of messages."""
        pass
    
    @abstractmethod
    async def structured_response(self, messages: List[Dict[str, str]], 
                                  response_model: BaseModel
                                  ) -> BaseModel:
        """Generate a structured response conforming to the given response model."""
        pass

# === OpenAI Chat Model Implementation ===
class OpenAIChatModel(BaseChatModel):
    async def generate_response(self, messages: List[Dict[str, str]],
                                tools:Optional[List[Dict]]=None,
                                stop:Optional[List[str]]=None,
                                callbacks:Optional[Any]=None,
                                **kwargs
                                ) -> Response:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            stop=stop,
            **kwargs
        )
        return Response(
            content=response.choices[0].message.content or "",
            token_usage=_usage_to_dict(getattr(response, "usage", None)),
            raw_response=response
        )
    
    async def stream_response(self, messages: List[Dict[str, str]],
                                tools:Optional[List[Dict]]=None,
                                stop:Optional[List[str]]=None,
                                callbacks:Optional[Any]=None,
                                **kwargs
                              ) -> AsyncIterator[str]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            stop=stop,
            stream=True,
            **kwargs
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text
    
    async def structured_response(self, messages: List[Dict[str, str]], 
                                  response_model: BaseModel
                                  ) -> BaseModel:
        response = await self.generate_response(messages)
        return response_model.parse_raw(response.content)


async def main():
    chat_model = OpenAIChatModel(api_key=API_KEY, base_url=BASE_URL, model=MODEL)
    test_message = {"role": "user", "content": "Hello, how are you?"}
    response = await chat_model.generate_response([test_message])
    print("Response from model:", response.content)
    print("Token usage:", response.token_usage)
    print("Raw response:", response.raw_response)


if __name__ == "__main__":
    asyncio.run(main())