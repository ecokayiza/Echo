from dataclasses import dataclass

from ..config import Config
from .chat_model import BaseChatModel, OpenAIChatModel


@dataclass(frozen=True)
class ChatModelSettings:
    provider: str = "openai_compatible"
    model: str | None = Config.MODEL
    api_key: str | None = Config.API_KEY
    base_url: str | None = Config.BASE_URL
    temperature: float = 1.0


def build_chat_model(settings: ChatModelSettings | None = None) -> BaseChatModel:
    resolved = settings or ChatModelSettings()
    providers = {
        "openai_compatible": OpenAIChatModel,
    }

    try:
        model_cls = providers[resolved.provider]
    except KeyError as exc:
        supported = ", ".join(sorted(providers))
        raise ValueError(f"Unsupported chat provider '{resolved.provider}'. Supported providers: {supported}") from exc

    return model_cls(
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        model=resolved.model,
        temperature=resolved.temperature,
    )
