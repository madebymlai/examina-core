# Rate Limiting System for Examina

## Overview

Examina now includes a **provider-agnostic rate limiting system** that automatically tracks and throttles LLM API usage across all providers. This prevents hitting API rate limits during analysis and ensures smooth operation with any LLM provider.

## Key Features

### 1. Provider-Agnostic Design
- **No hardcoded provider names** in logic
- Works with ANY current or future LLM provider
- Easy to add new providers via configuration only

### 2. Sliding Window Tracking
- Uses 60-second sliding windows (not fixed boundaries)
- Tracks both requests per minute AND tokens per minute
- Automatic cleanup of old entries

### 3. Automatic Throttling
- Automatically waits when rate limits would be exceeded
- Transparent to the user (just shows waiting time)
- No manual rate limit management needed

### 4. Thread-Safe Operations
- Uses threading locks for concurrent requests
- Safe for parallel processing

### 5. Persistent State
- Caches usage across CLI runs
- Resumes tracking after restart
- Stored in `data/cache/rate_limits.json`

## Configuration

### Default Limits (config.py)

```python
PROVIDER_RATE_LIMITS = {
    "anthropic": {
        "requests_per_minute": 50,
        "tokens_per_minute": 40000,
        "burst_size": 5
    },
    "groq": {
        "requests_per_minute": 30,  # Free tier
        "tokens_per_minute": 6000,   # Free tier
        "burst_size": 3
    },
    "ollama": {
        "requests_per_minute": None,  # Unlimited (local)
        "tokens_per_minute": None,
        "burst_size": 1
    },
    "openai": {
        "requests_per_minute": 60,
        "tokens_per_minute": 90000,
        "burst_size": 5
    }
}
```

### Environment Variable Override

You can customize limits without modifying code:

```bash
# Groq settings
export GROQ_RPM=30        # Requests per minute
export GROQ_TPM=6000      # Tokens per minute

# Anthropic settings
export ANTHROPIC_RPM=50
export ANTHROPIC_TPM=40000

# OpenAI settings
export OPENAI_RPM=60
export OPENAI_TPM=90000
```

### Adding a New Provider

Simply add it to `config.py`:

```python
PROVIDER_RATE_LIMITS = {
    # ... existing providers ...
    "my_new_provider": {
        "requests_per_minute": 100,
        "tokens_per_minute": 50000,
        "burst_size": 10
    }
}
```

No code changes needed anywhere else!

## Usage

### Automatic Rate Limiting

Rate limiting happens **automatically** when you use any Examina command:

```bash
# Analysis automatically throttles if needed
examina analyze --course B006802 --provider groq

# Quiz commands respect rate limits
examina quiz --course B006802 --provider anthropic
```

### Viewing Rate Limit Status

Check current usage:

```bash
# View all providers
examina rate-limits

# View specific provider
examina rate-limits --provider groq

# Reset tracking (if needed)
examina rate-limits --reset
examina rate-limits --provider groq --reset
```

### Example Output

```
API Rate Limit Status

╭──────────────────────────────── 📊 Groq ─────────────────────────────────╮
│ Provider: groq                                                           │
│ Current Provider: ✓ Active                                               │
│                                                                          │
│ Requests (per minute):                                                   │
│   Used: 25/30 (83.3%)                                                    │
│   Remaining: 5                                                           │
│                                                                          │
│ Tokens (per minute):                                                     │
│   Used: 4,500/6,000 (75.0%)                                              │
│   Remaining: 1,500                                                       │
│                                                                          │
│ Time until reset: 15.2s                                                  │
╰──────────────────────────────────────────────────────────────────────────╯
```

## How It Works

### Architecture

```
┌─────────────┐
│   CLI/App   │
└──────┬──────┘
       │ generate()
       ▼
┌─────────────────┐
│  LLMManager     │  1. Check rate limit
│                 │  2. Wait if needed
│                 │  3. Make API call
│                 │  4. Record usage
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│  RateLimitTracker   │
│                     │
│  • Sliding windows  │
│  • Thread-safe      │
│  • Persistent cache │
└─────────────────────┘
```

### Request Flow

1. **Before Request**: `wait_if_needed(provider)` checks if rate limit would be exceeded
2. **If Exceeding**: Automatically sleeps until oldest request expires
3. **API Call**: Makes the actual request
4. **After Request**: `record_request(provider, tokens)` tracks usage
5. **Cache**: Saves state to disk for persistence

### Sliding Window Algorithm

```python
# Example: 30 requests per minute limit

Requests:  [t-55s] [t-50s] [t-45s] ... [t-5s] [NOW]
           ────────────────────────────────────────
           ←───────── 60 second window ──────────→

# Old requests (> 60s ago) are automatically removed
# Only requests in last 60 seconds count toward limit
```

## Integration with LLMManager

Rate limiting is integrated at the `LLMManager.generate()` level, so all code using the LLM automatically benefits:

```python
from models.llm_manager import LLMManager

llm = LLMManager(provider="groq")

# Rate limiting happens automatically
response = llm.generate(
    prompt="Analyze this exercise",
    model=llm.primary_model
)

# Usage is tracked automatically
stats = llm.get_rate_limit_stats()
print(f"Used {stats['requests']['used']}/{stats['requests']['limit']} requests")
```

## API Reference

### RateLimitTracker

```python
class RateLimitTracker:
    """Generic rate limiting tracker for any LLM provider."""

    def __init__(self, provider_limits: Dict[str, Dict],
                 cache_path: Optional[Path] = None):
        """
        Initialize with provider limits.

        Args:
            provider_limits: Dict mapping provider names to their limits
            cache_path: Optional path for persistent cache
        """

    def check_limit(self, provider: str) -> bool:
        """Check if provider is within rate limits."""

    def record_request(self, provider: str, tokens_used: int = 0):
        """Record a request for rate tracking."""

    def wait_if_needed(self, provider: str) -> float:
        """Wait if rate limit would be exceeded. Returns wait time."""

    def get_usage_stats(self, provider: str) -> Dict[str, Any]:
        """Get current usage statistics."""

    def reset(self, provider: str):
        """Reset tracking for a provider."""

    def reset_all(self):
        """Reset tracking for all providers."""
```

### LLMManager Extensions

```python
def get_rate_limit_stats(self, provider: Optional[str] = None) -> Dict[str, Any]:
    """Get rate limit statistics for a provider."""

def get_all_rate_limit_stats(self) -> Dict[str, Dict[str, Any]]:
    """Get rate limit statistics for all providers."""
```

## Testing

### Run Tests

```bash
# Basic functionality test
python scripts/test_rate_limiting.py

# Generic design test (no hardcoding)
python scripts/test_generic_rate_limiting.py
```

### Test Results

✅ Automatic throttling when limits exceeded
✅ Token counting (when available from API)
✅ Multi-provider tracking
✅ Persistent cache across runs
✅ Thread-safe concurrent requests
✅ No hardcoded provider names
✅ Works with hypothetical future providers

## Performance Impact

- **Minimal overhead**: ~1-2ms per request
- **Cache**: Loads once at initialization, saves after each request
- **Memory**: ~100 bytes per tracked request (max 60 seconds of history)
- **Disk**: Single JSON file, ~10KB typical size

## Edge Cases Handled

1. **Provider not configured**: Gracefully skips rate limiting
2. **No limits (local providers)**: Tracks but doesn't throttle
3. **Cache corruption**: Falls back to empty state
4. **Concurrent requests**: Thread-safe operations
5. **API returns no token count**: Falls back to request counting only
6. **CLI restart**: Resumes from persisted state

## Troubleshooting

### Rate Limits Not Working

Check configuration:
```bash
examina rate-limits
```

Verify your provider is configured:
```python
from config import Config
print(Config.PROVIDER_RATE_LIMITS)
```

### Still Hitting API Rate Limits

Reduce configured limits to be more conservative:
```bash
export GROQ_RPM=25  # Lower than actual 30 to be safe
```

### Cache Issues

Clear cache and restart:
```bash
rm data/cache/rate_limits.json
examina rate-limits --reset
```

## Future Enhancements

Potential improvements:

- [ ] Adaptive rate limiting (learn from 429 errors)
- [ ] Per-model limits (different models may have different limits)
- [ ] Priority queuing (prioritize important requests)
- [ ] Distributed rate limiting (multiple machines)
- [ ] Usage analytics and reports

## Compliance

This system helps ensure compliance with API provider terms of service by:
- Preventing accidental rate limit violations
- Tracking usage for billing estimates
- Providing visibility into API consumption
- Supporting multiple API keys (for higher limits)

## License

Same as Examina (see main repository LICENSE)
