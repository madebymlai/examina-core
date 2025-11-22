"""
LLM Manager for Examina.
Handles interactions with Ollama and other LLM providers.
"""

import json
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from config import Config


@dataclass
class LLMResponse:
    """Response from LLM."""
    text: str
    model: str
    success: bool
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMManager:
    """Manages LLM interactions for Examina."""

    def __init__(self, provider: str = "ollama", base_url: Optional[str] = None):
        """Initialize LLM manager.

        Args:
            provider: LLM provider ("ollama", "anthropic", "openai")
            base_url: Base URL for API (for Ollama)
        """
        self.provider = provider
        self.base_url = base_url or Config.OLLAMA_BASE_URL

        # Model selection
        self.primary_model = Config.LLM_PRIMARY_MODEL  # Heavy reasoning
        self.fast_model = Config.LLM_FAST_MODEL  # Quick tasks
        self.embed_model = Config.LLM_EMBED_MODEL  # Embeddings

    def generate(self, prompt: str, model: Optional[str] = None,
                 system: Optional[str] = None,
                 temperature: float = 0.7,
                 max_tokens: Optional[int] = None,
                 json_mode: bool = False) -> LLMResponse:
        """Generate text from LLM.

        Args:
            prompt: User prompt
            model: Model to use (defaults to fast_model)
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            json_mode: Force JSON output

        Returns:
            LLMResponse with generated text
        """
        model = model or self.fast_model

        if self.provider == "ollama":
            return self._ollama_generate(
                prompt, model, system, temperature, max_tokens, json_mode
            )
        else:
            return LLMResponse(
                text="",
                model=model,
                success=False,
                error=f"Provider {self.provider} not implemented yet"
            )

    def _ollama_generate(self, prompt: str, model: str,
                        system: Optional[str], temperature: float,
                        max_tokens: Optional[int], json_mode: bool) -> LLMResponse:
        """Generate using Ollama API.

        Args:
            prompt: User prompt
            model: Model name
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            json_mode: Force JSON output

        Returns:
            LLMResponse
        """
        try:
            url = f"{self.base_url}/api/generate"

            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                }
            }

            if system:
                payload["system"] = system

            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            if json_mode:
                payload["format"] = "json"

            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()

            result = response.json()

            return LLMResponse(
                text=result.get("response", ""),
                model=model,
                success=True,
                metadata={
                    "total_duration": result.get("total_duration"),
                    "load_duration": result.get("load_duration"),
                    "eval_count": result.get("eval_count"),
                }
            )

        except requests.exceptions.ConnectionError:
            return LLMResponse(
                text="",
                model=model,
                success=False,
                error="Cannot connect to Ollama. Is it running? (ollama serve)"
            )
        except requests.exceptions.Timeout:
            return LLMResponse(
                text="",
                model=model,
                success=False,
                error="Request timed out. Model might be too slow."
            )
        except Exception as e:
            return LLMResponse(
                text="",
                model=model,
                success=False,
                error=f"Ollama error: {str(e)}"
            )

    def embed(self, text: str, model: Optional[str] = None) -> Optional[List[float]]:
        """Generate embeddings for text.

        Args:
            text: Text to embed
            model: Embedding model (defaults to embed_model)

        Returns:
            List of floats (embedding vector) or None on error
        """
        model = model or self.embed_model

        if self.provider == "ollama":
            return self._ollama_embed(text, model)
        else:
            return None

    def _ollama_embed(self, text: str, model: str) -> Optional[List[float]]:
        """Generate embeddings using Ollama.

        Args:
            text: Text to embed
            model: Model name

        Returns:
            Embedding vector or None
        """
        try:
            url = f"{self.base_url}/api/embeddings"

            payload = {
                "model": model,
                "prompt": text
            }

            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()

            result = response.json()
            return result.get("embedding")

        except Exception as e:
            print(f"Embedding error: {e}")
            return None

    def check_model_available(self, model: str) -> bool:
        """Check if a model is available locally.

        Args:
            model: Model name

        Returns:
            True if model is available
        """
        if self.provider == "ollama":
            try:
                url = f"{self.base_url}/api/tags"
                response = requests.get(url, timeout=10)
                response.raise_for_status()

                models = response.json().get("models", [])
                available_models = [m["name"] for m in models]

                return model in available_models

            except Exception:
                return False
        return False

    def list_available_models(self) -> List[str]:
        """List all available models.

        Returns:
            List of model names
        """
        if self.provider == "ollama":
            try:
                url = f"{self.base_url}/api/tags"
                response = requests.get(url, timeout=10)
                response.raise_for_status()

                models = response.json().get("models", [])
                return [m["name"] for m in models]

            except Exception:
                return []
        return []

    def parse_json_response(self, response: LLMResponse) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response.

        Args:
            response: LLM response

        Returns:
            Parsed JSON dict or None on error
        """
        if not response.success:
            return None

        try:
            # Try to parse the entire response
            return json.loads(response.text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            text = response.text
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                json_str = text[start:end].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

            # Try to find JSON object in text
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            return None
