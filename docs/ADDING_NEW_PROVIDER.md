# Adding a New LLM Provider with Rate Limiting

This guide shows how to add a new LLM provider to Examina with full rate limiting support. The system is designed to be **provider-agnostic**, requiring only configuration changes.

## Step-by-Step Guide

### Step 1: Add Provider Configuration

Edit `config.py` and add your provider's rate limits:

```python
class Config:
    # ... existing config ...

    # Rate Limiting Settings
    PROVIDER_RATE_LIMITS = {
        "anthropic": { ... },
        "groq": { ... },
        "ollama": { ... },
        "openai": { ... },

        # NEW PROVIDER - Just add this!
        "my_new_provider": {
            "requests_per_minute": 100,      # Your provider's limit
            "tokens_per_minute": 50000,      # Your provider's limit
            "burst_size": 10                 # Allow small bursts
        }
    }
```

**That's it!** Rate limiting now works automatically.

### Step 2: (Optional) Add Environment Variable Override

For user customization, add environment variable support:

```python
"my_new_provider": {
    "requests_per_minute": int(os.getenv("MY_PROVIDER_RPM", "100")),
    "tokens_per_minute": int(os.getenv("MY_PROVIDER_TPM", "50000")),
    "burst_size": 10
}
```

Users can now override:
```bash
export MY_PROVIDER_RPM=150
export MY_PROVIDER_TPM=75000
```

### Step 3: Add Provider to LLMManager (if needed)

If you need to implement the actual API calls, add a method to `models/llm_manager.py`:

```python
def _my_provider_generate(self, prompt: str, model: str,
                          system: Optional[str], temperature: float,
                          max_tokens: Optional[int], json_mode: bool) -> LLMResponse:
    """Generate using My Provider API."""

    # Check cache first (optional but recommended)
    cache_key = self._generate_cache_key(
        provider="my_new_provider",
        model=model,
        prompt=prompt,
        system=system,
        temperature=temperature,
        json_mode=json_mode
    )
    cached_response = self._get_cached_response(cache_key)
    if cached_response:
        return cached_response

    try:
        # Your API call here
        response = requests.post(
            "https://api.my-provider.com/v1/generate",
            json={
                "prompt": prompt,
                "model": model,
                # ... your provider's format ...
            },
            headers={"Authorization": f"Bearer {Config.MY_PROVIDER_API_KEY}"}
        )

        result = response.json()

        llm_response = LLMResponse(
            text=result["output"],
            model=model,
            success=True,
            metadata={
                "usage": result.get("usage"),  # Include token counts if available
            }
        )

        # Cache successful response
        self._save_to_cache(cache_key, llm_response)

        return llm_response

    except Exception as e:
        return LLMResponse(
            text="",
            model=model,
            success=False,
            error=f"My Provider error: {str(e)}"
        )
```

Add it to the `generate()` method:

```python
def generate(self, prompt: str, model: Optional[str] = None, ...) -> LLMResponse:
    """Generate text from LLM."""
    model = model or self.fast_model

    # Apply rate limiting (automatic!)
    wait_time = self.rate_limiter.wait_if_needed(self.provider)
    if wait_time > 0:
        print(f"  [RATE LIMIT] Waiting {wait_time:.1f}s...")

    # Route to provider
    if self.provider == "my_new_provider":
        response = self._my_provider_generate(prompt, model, ...)
    elif self.provider == "ollama":
        response = self._ollama_generate(prompt, model, ...)
    # ... other providers ...

    # Record usage (automatic!)
    if response.success:
        tokens_used = 0
        if response.metadata:
            usage = response.metadata.get("usage", {})
            if isinstance(usage, dict):
                tokens_used = usage.get("total_tokens", 0)
        self.rate_limiter.record_request(self.provider, tokens_used=tokens_used)

    return response
```

## Complete Example: Adding "Cohere"

Let's add Cohere as a complete example:

### 1. Configuration (`config.py`)

```python
class Config:
    # API Keys
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")

    # Rate limits
    PROVIDER_RATE_LIMITS = {
        # ... existing providers ...
        "cohere": {
            "requests_per_minute": int(os.getenv("COHERE_RPM", "100")),
            "tokens_per_minute": int(os.getenv("COHERE_TPM", "100000")),
            "burst_size": 10
        }
    }
```

### 2. LLMManager Support

```python
def __init__(self, provider: str = "ollama", base_url: Optional[str] = None):
    # ... existing init ...

    # Model selection
    if provider == "cohere":
        self.primary_model = os.getenv("COHERE_MODEL", "command-r-plus")
        self.fast_model = os.getenv("COHERE_FAST_MODEL", "command")
        self.embed_model = Config.LLM_EMBED_MODEL  # Use Ollama for embeddings
    # ... other providers ...
```

### 3. API Implementation

```python
def _cohere_generate(self, prompt: str, model: str,
                     system: Optional[str], temperature: float,
                     max_tokens: Optional[int], json_mode: bool) -> LLMResponse:
    """Generate using Cohere API."""

    if not Config.COHERE_API_KEY:
        return LLMResponse(
            text="",
            model=model,
            success=False,
            error="COHERE_API_KEY not set"
        )

    # Check cache
    cache_key = self._generate_cache_key("cohere", model, prompt, system, temperature, json_mode)
    cached = self._get_cached_response(cache_key)
    if cached:
        return cached

    try:
        url = "https://api.cohere.ai/v1/generate"

        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096
        }

        if system:
            payload["prompt"] = f"{system}\n\n{prompt}"

        headers = {
            "Authorization": f"Bearer {Config.COHERE_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()

        result = response.json()

        llm_response = LLMResponse(
            text=result["generations"][0]["text"],
            model=model,
            success=True,
            metadata={
                "usage": {
                    "total_tokens": result.get("meta", {}).get("billed_units", {}).get("input_tokens", 0) +
                                   result.get("meta", {}).get("billed_units", {}).get("output_tokens", 0)
                }
            }
        )

        self._save_to_cache(cache_key, llm_response)
        return llm_response

    except Exception as e:
        return LLMResponse(text="", model=model, success=False, error=f"Cohere error: {str(e)}")
```

### 4. Add to generate() router

```python
def generate(self, prompt: str, ...) -> LLMResponse:
    # ... rate limiting ...

    if self.provider == "cohere":
        response = self._cohere_generate(prompt, model, system, temperature, max_tokens, json_mode)
    elif self.provider == "groq":
        # ... existing code ...
```

### 5. Usage

```bash
# Set API key
export COHERE_API_KEY=your_key_here

# Use with any command
examina analyze --course B006802 --provider cohere

# Check rate limits
examina rate-limits --provider cohere
```

**Done!** Rate limiting works automatically with zero additional code.

## No Hardcoding - The Key Principle

Notice that:

1. ❌ **No hardcoded provider names in rate_limiter.py**
2. ❌ **No hardcoded rate limits in code**
3. ❌ **No if/else chains for specific providers**
4. ✅ **All configuration in config.py**
5. ✅ **Environment variable overrides**
6. ✅ **Works with any future provider**

### Testing Your New Provider

```python
# Test rate limiting works
from models.llm_manager import LLMManager

llm = LLMManager(provider="cohere")

# Make some requests
for i in range(5):
    response = llm.generate("Hello")
    stats = llm.get_rate_limit_stats()
    print(f"Used: {stats['requests']['used']}/{stats['requests']['limit']}")
```

## Special Cases

### Local/Unlimited Provider

For local models with no rate limits:

```python
"my_local_model": {
    "requests_per_minute": None,  # Unlimited
    "tokens_per_minute": None,
    "burst_size": 1
}
```

### Very Strict Limits

For providers with very low limits:

```python
"strict_provider": {
    "requests_per_minute": 5,   # Only 5 per minute
    "tokens_per_minute": 1000,
    "burst_size": 1             # No bursting
}
```

The system will automatically throttle appropriately.

### Provider-Specific Token Counting

If your provider returns tokens in a different format:

```python
# In your _provider_generate() method
llm_response = LLMResponse(
    text=result["output"],
    model=model,
    success=True,
    metadata={
        "usage": {
            "total_tokens": result["custom_token_field"]  # Adapt to your format
        }
    }
)
```

The rate limiter will automatically use this for token tracking.

## Verification Checklist

After adding a provider, verify:

- [ ] Configuration added to `PROVIDER_RATE_LIMITS`
- [ ] Environment variable overrides work (optional)
- [ ] API key configuration added
- [ ] API implementation returns token counts in metadata
- [ ] Rate limiting works: `examina rate-limits --provider my_provider`
- [ ] Throttling occurs when limits exceeded (test with many requests)
- [ ] No hardcoded logic added to rate_limiter.py

## Getting Help

If you run into issues:

1. Check configuration: `examina rate-limits`
2. Test with small limits to verify throttling
3. Check logs for rate limit messages
4. Verify token counts are being tracked

## Contributing

When contributing new providers, please:

1. Follow the provider-agnostic pattern
2. Add rate limit configuration
3. Document the provider's actual limits
4. Test with the test scripts
5. Update documentation

Your provider will automatically benefit from:
- Automatic throttling
- Usage tracking
- Persistent cache
- Thread-safe operations
- CLI commands for monitoring
