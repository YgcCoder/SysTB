"""
Model client: unified interface for multiple LLM providers (OpenAI-compatible, Anthropic, Google).
API keys are read from configs/models.yaml — do NOT hard-code keys here.
"""
import yaml
import time
import logging
from typing import Dict, Optional, Any
from pathlib import Path
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseModelClient(ABC):
    """Abstract base class for all model clients."""

    def __init__(self, model_config: Dict[str, Any]):
        self.model_id = model_config['model_id']
        self.model_name = model_config['model_name']
        self.api_config = model_config['api_config']
        self.generation_config = model_config.get('generation_config', {})
        self.enabled = model_config.get('enabled', True)

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate a response from the model."""
        pass

    def generate_with_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: int = 5,
        **kwargs,
    ) -> str:
        """Call generate() with automatic retry on failure."""
        for attempt in range(max_retries):
            try:
                return self.generate(prompt, system_prompt, **kwargs)
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise


class OpenAIClient(BaseModelClient):
    """Client for OpenAI and OpenAI-compatible APIs."""

    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_config['api_key'],
                base_url=self.api_config.get('base_url', 'https://api.openai.com/v1'),
                organization=self.api_config.get('organization'),
            )
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        params = {**self.generation_config, **kwargs}
        # GPT-5.x uses max_completion_tokens instead of max_tokens
        if self.model_name in ['gpt-5.2', 'gpt-5.1'] and 'max_tokens' in params:
            params['max_completion_tokens'] = params.pop('max_tokens')

        response = self.client.chat.completions.create(model=self.model_name, messages=messages, **params)
        return response.choices[0].message.content


class AnthropicClient(BaseModelClient):
    """Client for Anthropic Claude API."""

    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_config['api_key'])
        except ImportError:
            raise ImportError("Please install anthropic: pip install anthropic")

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        params = {**self.generation_config, **kwargs}
        message_params = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            **params,
        }
        if system_prompt:
            message_params["system"] = system_prompt
        response = self.client.messages.create(**message_params)
        return response.content[0].text


class GoogleClient(BaseModelClient):
    """Client for Google Gemini API."""

    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_config['api_key'])
            self.model = genai.GenerativeModel(self.model_name)
        except ImportError:
            raise ImportError("Please install google-generativeai: pip install google-generativeai")

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        params = {**self.generation_config, **kwargs}
        response = self.model.generate_content(full_prompt, generation_config=params)
        return response.text


class ModelClientFactory:
    """Factory for creating model clients from configs/models.yaml."""

    PROVIDER_MAP = {
        'openai': OpenAIClient,
        'anthropic': AnthropicClient,
        'google': GoogleClient,
        'openai_compatible': OpenAIClient,
    }

    @staticmethod
    def create_client(model_config: Dict[str, Any]) -> BaseModelClient:
        provider = model_config.get('provider', 'openai')
        client_class = ModelClientFactory.PROVIDER_MAP.get(provider)
        if not client_class:
            raise ValueError(f"Unsupported provider: {provider}")
        return client_class(model_config)

    @staticmethod
    def load_models_config(config_path: str) -> Dict[str, BaseModelClient]:
        """Load all enabled model clients from a YAML config file."""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        clients = {}
        for model_config in config['models']:
            if model_config.get('enabled', True):
                model_id = model_config['model_id']
                try:
                    clients[model_id] = ModelClientFactory.create_client(model_config)
                    logger.info(f"Loaded model client: {model_id}")
                except Exception as e:
                    logger.error(f"Failed to load model {model_id}: {e}")
        return clients
