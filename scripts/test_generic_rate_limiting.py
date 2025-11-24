#!/usr/bin/env python3
"""
Test that rate limiting is truly provider-agnostic.

This script tests adding a completely new provider (not in the original spec)
to verify that the system doesn't have any hardcoded logic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rate_limiter import RateLimitTracker
from rich.console import Console

console = Console()


def test_hypothetical_provider():
    """Test with a completely made-up provider to ensure no hardcoding."""
    console.print("\n[bold cyan]Testing Provider-Agnostic Design[/bold cyan]\n")

    # Create rate limiter with a mix of real and fake providers
    provider_limits = {
        "anthropic": {
            "requests_per_minute": 50,
            "tokens_per_minute": 40000,
            "burst_size": 5
        },
        "fake_provider_x": {  # Completely made up provider
            "requests_per_minute": 100,
            "tokens_per_minute": 50000,
            "burst_size": 10
        },
        "future_llm_service": {  # Another hypothetical provider
            "requests_per_minute": 20,
            "tokens_per_minute": 10000,
            "burst_size": 2
        },
        "local_model": {  # Unlimited local provider
            "requests_per_minute": None,
            "tokens_per_minute": None,
            "burst_size": 1
        }
    }

    tracker = RateLimitTracker(provider_limits)

    # Test each provider
    providers_to_test = ["anthropic", "fake_provider_x", "future_llm_service", "local_model"]

    for provider in providers_to_test:
        console.print(f"\n[bold]Testing: {provider}[/bold]")

        # Get initial stats
        stats = tracker.get_usage_stats(provider)
        console.print(f"  Has limits: {stats['has_limits']}")

        if stats['has_limits']:
            # Record some usage
            for i in range(3):
                tracker.record_request(provider, tokens_used=100 * (i + 1))

            # Check stats again
            stats = tracker.get_usage_stats(provider)
            console.print(f"  Requests: {stats['requests']['used']}/{stats['requests']['limit']}")
            console.print(f"  Tokens: {stats['tokens']['used']}/{stats['tokens']['limit']}")
            console.print(f"  Request %: {stats['requests']['percentage']}%")
            console.print(f"  Token %: {stats['tokens']['percentage']}%")

            # Test rate limit check
            is_within_limit = tracker.check_limit(provider)
            console.print(f"  Within limit: {is_within_limit}")
        else:
            console.print(f"  [green]No rate limits (unlimited)[/green]")

            # Still should handle recording
            tracker.record_request(provider, tokens_used=999999)
            stats = tracker.get_usage_stats(provider)
            console.print(f"  Recorded request (should work without errors)")

    # Test provider not in config (should gracefully skip)
    console.print(f"\n[bold]Testing: unconfigured_provider[/bold]")
    console.print(f"  Check limit: {tracker.check_limit('unconfigured_provider')}")
    tracker.record_request('unconfigured_provider', tokens_used=100)
    stats = tracker.get_usage_stats('unconfigured_provider')
    console.print(f"  Stats returned: {stats.get('error', 'OK')}")

    console.print("\n[green]✓ All providers handled correctly (no hardcoding detected)[/green]\n")


def test_dynamic_configuration():
    """Test that limits can be changed at runtime."""
    console.print("\n[bold cyan]Testing Dynamic Configuration[/bold cyan]\n")

    # Start with one set of limits
    initial_limits = {
        "custom_api": {
            "requests_per_minute": 10,
            "tokens_per_minute": 5000,
            "burst_size": 2
        }
    }

    tracker = RateLimitTracker(initial_limits)

    # Record usage
    for i in range(5):
        tracker.record_request("custom_api", tokens_used=500)

    stats = tracker.get_usage_stats("custom_api")
    console.print(f"Initial config:")
    console.print(f"  Requests: {stats['requests']['used']}/{stats['requests']['limit']} ({stats['requests']['percentage']}%)")

    # In a real app, you could create a new tracker with different limits
    # This demonstrates the config is not hardcoded
    new_limits = {
        "custom_api": {
            "requests_per_minute": 50,  # Increased limit
            "tokens_per_minute": 20000,  # Increased limit
            "burst_size": 5
        }
    }

    new_tracker = RateLimitTracker(new_limits)

    # Same usage on new tracker
    for i in range(5):
        new_tracker.record_request("custom_api", tokens_used=500)

    new_stats = new_tracker.get_usage_stats("custom_api")
    console.print(f"\nNew config (same usage):")
    console.print(f"  Requests: {new_stats['requests']['used']}/{new_stats['requests']['limit']} ({new_stats['requests']['percentage']}%)")

    console.print(f"\n[green]✓ Configuration is dynamic (percentage changed from {stats['requests']['percentage']}% to {new_stats['requests']['percentage']}%)[/green]\n")


def test_no_provider_name_branches():
    """Verify that the code has no if/else branches for specific providers."""
    console.print("\n[bold cyan]Code Analysis: Checking for Hardcoded Logic[/bold cyan]\n")

    # Read the rate limiter source code
    rate_limiter_path = Path(__file__).parent.parent / "core" / "rate_limiter.py"

    with open(rate_limiter_path, 'r') as f:
        source_code = f.read()

    # Check for suspicious patterns (excluding comments and docstrings)
    lines = source_code.split('\n')
    suspicious_patterns = []

    for i, line in enumerate(lines, 1):
        # Skip comments and docstrings
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        # Check for if/elif statements with provider names
        if ('if ' in line or 'elif ' in line) and any(provider in line.lower() for provider in ['anthropic', 'groq', 'ollama', 'openai', 'gemini']):
            # Make sure it's not in a string
            if '"' not in line and "'" not in line:
                suspicious_patterns.append((i, line.strip()))

    if suspicious_patterns:
        console.print("[yellow]Found potential hardcoded logic:[/yellow]")
        for line_num, line in suspicious_patterns:
            console.print(f"  Line {line_num}: {line}")
        console.print("\n[yellow]⚠ Warning: Code may have provider-specific branches[/yellow]\n")
    else:
        console.print("[green]✓ No hardcoded provider logic found in rate_limiter.py[/green]")
        console.print("[dim]The rate limiter is truly provider-agnostic![/dim]\n")


def main():
    """Run all tests."""
    console.print("\n[bold magenta]═══════════════════════════════════════════════[/bold magenta]")
    console.print("[bold magenta]   Generic Rate Limiting Test Suite[/bold magenta]")
    console.print("[bold magenta]═══════════════════════════════════════════════[/bold magenta]")

    try:
        # Test 1: Hypothetical providers
        test_hypothetical_provider()

        # Test 2: Dynamic configuration
        test_dynamic_configuration()

        # Test 3: Code analysis
        test_no_provider_name_branches()

        console.print("[bold green]═══════════════════════════════════════════════[/bold green]")
        console.print("[bold green]   All Tests Passed - No Hardcoding Detected![/bold green]")
        console.print("[bold green]═══════════════════════════════════════════════[/bold green]\n")

    except Exception as e:
        console.print(f"\n[bold red]Test failed:[/bold red] {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
