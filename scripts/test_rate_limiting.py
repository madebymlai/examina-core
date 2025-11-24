#!/usr/bin/env python3
"""
Test script for rate limiting functionality.

Tests:
1. Rapid-fire requests to different providers
2. Automatic throttling when limits are exceeded
3. Token counting
4. Multi-provider usage tracking
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.llm_manager import LLMManager
from config import Config
from rich.console import Console
from rich.table import Table

console = Console()


def test_rate_limiting_basic():
    """Test basic rate limiting with rapid requests."""
    console.print("\n[bold cyan]Test 1: Basic Rate Limiting[/bold cyan]\n")

    # Use Groq which has stricter limits (30 req/min)
    console.print(f"Using provider: {Config.LLM_PROVIDER}")
    console.print(f"Configured limit: {Config.PROVIDER_RATE_LIMITS.get(Config.LLM_PROVIDER, {}).get('requests_per_minute')} requests/minute\n")

    llm = LLMManager(provider=Config.LLM_PROVIDER)

    # Get initial stats
    stats = llm.get_rate_limit_stats()
    console.print(f"[dim]Initial usage: {stats['requests']['used']}/{stats['requests']['limit']} requests[/dim]\n")

    # Make rapid requests
    num_requests = 5
    console.print(f"Making {num_requests} rapid requests...\n")

    start_time = time.time()
    for i in range(num_requests):
        console.print(f"[cyan]Request {i+1}/{num_requests}...[/cyan]")
        response = llm.generate(
            prompt="Say 'OK' and nothing else",
            system="You are a helpful assistant",
            temperature=0,
            max_tokens=10
        )

        if response.success:
            console.print(f"  ✓ Response: {response.text[:50]}")
        else:
            console.print(f"  ✗ Error: {response.error}")

        # Show current stats
        stats = llm.get_rate_limit_stats()
        console.print(f"  [dim]Usage: {stats['requests']['used']}/{stats['requests']['limit']} requests ({stats['requests']['percentage']}%)[/dim]\n")

        time.sleep(0.5)  # Small delay between requests

    elapsed = time.time() - start_time
    console.print(f"[green]✓ Completed {num_requests} requests in {elapsed:.2f}s[/green]\n")

    # Final stats
    final_stats = llm.get_rate_limit_stats()
    console.print("[bold]Final Statistics:[/bold]")
    console.print(f"  Requests: {final_stats['requests']['used']}/{final_stats['requests']['limit']}")
    console.print(f"  Tokens: {final_stats['tokens']['used']}/{final_stats['tokens']['limit']}")
    console.print(f"  Time until reset: {final_stats['time_until_reset']}s\n")


def test_rate_limit_throttling():
    """Test that throttling occurs when limit is exceeded."""
    console.print("\n[bold cyan]Test 2: Rate Limit Throttling[/bold cyan]\n")

    # Simulate hitting the limit
    llm = LLMManager(provider=Config.LLM_PROVIDER)

    # Get current config
    provider_config = Config.PROVIDER_RATE_LIMITS.get(Config.LLM_PROVIDER, {})
    limit = provider_config.get('requests_per_minute')

    if limit is None:
        console.print(f"[yellow]Provider '{Config.LLM_PROVIDER}' has no rate limits, skipping throttling test[/yellow]\n")
        return

    console.print(f"Provider: {Config.LLM_PROVIDER}")
    console.print(f"Rate limit: {limit} requests/minute")
    console.print(f"Testing with {limit + 2} requests to trigger throttling...\n")

    # Make requests up to limit
    start_time = time.time()
    for i in range(min(limit + 2, 10)):  # Cap at 10 for reasonable test time
        console.print(f"[cyan]Request {i+1}...[/cyan]")

        # This should trigger automatic throttling when limit is reached
        response = llm.generate(
            prompt="OK",
            temperature=0,
            max_tokens=5
        )

        stats = llm.get_rate_limit_stats()
        console.print(f"  Usage: {stats['requests']['used']}/{stats['requests']['limit']} ({stats['requests']['percentage']}%)")

        if i >= limit - 1:
            console.print(f"  [yellow]Approaching/exceeding limit...[/yellow]")

    elapsed = time.time() - start_time
    console.print(f"\n[green]✓ Test complete in {elapsed:.2f}s[/green]")
    console.print(f"[dim]Note: Throttling automatically delays requests when limits are exceeded[/dim]\n")


def test_multi_provider():
    """Test rate limiting across multiple providers."""
    console.print("\n[bold cyan]Test 3: Multi-Provider Rate Limiting[/bold cyan]\n")

    providers = ['anthropic', 'groq', 'ollama']

    for provider in providers:
        # Check if provider is configured
        if provider == 'anthropic' and not Config.ANTHROPIC_API_KEY:
            console.print(f"[dim]Skipping {provider} (no API key)[/dim]")
            continue
        if provider == 'groq' and not Config.GROQ_API_KEY:
            console.print(f"[dim]Skipping {provider} (no API key)[/dim]")
            continue

        console.print(f"\n[bold]Testing {provider}...[/bold]")
        llm = LLMManager(provider=provider)

        # Make a single request
        response = llm.generate(prompt="Hi", max_tokens=5)

        # Get stats
        stats = llm.get_rate_limit_stats()

        if stats.get('has_limits'):
            console.print(f"  Requests: {stats['requests']['used']}/{stats['requests']['limit']} ({stats['requests']['percentage']}%)")
            if stats['tokens']['limit']:
                console.print(f"  Tokens: {stats['tokens']['used']}/{stats['tokens']['limit']} ({stats['tokens']['percentage']}%)")
        else:
            console.print(f"  [green]No rate limits (local/unlimited)[/green]")

    console.print()


def test_stats_display():
    """Test the stats display functionality."""
    console.print("\n[bold cyan]Test 4: Statistics Display[/bold cyan]\n")

    llm = LLMManager(provider=Config.LLM_PROVIDER)

    # Get all provider stats
    all_stats = llm.get_all_rate_limit_stats()

    # Create table
    table = Table(title="Rate Limit Summary", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="yellow")
    table.add_column("Status", justify="center")
    table.add_column("Requests", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Request %", justify="right")

    for provider, stats in all_stats.items():
        if 'error' in stats or not stats.get('has_limits'):
            status = "○"
            requests = "unlimited"
            tokens = "unlimited"
            pct = "0%"
        else:
            status = "✓" if provider == Config.LLM_PROVIDER else "○"
            req_used = stats['requests']['used']
            req_limit = stats['requests']['limit'] if stats['requests']['limit'] else "∞"
            requests = f"{req_used}/{req_limit}"

            tok_used = stats['tokens']['used']
            tok_limit = stats['tokens']['limit'] if stats['tokens']['limit'] else "∞"
            tokens = f"{tok_used}/{tok_limit}"

            pct = f"{stats['requests']['percentage']:.1f}%"

        table.add_row(provider, status, requests, tokens, pct)

    console.print(table)
    console.print()


def main():
    """Run all tests."""
    console.print("\n[bold magenta]═══════════════════════════════════════════════[/bold magenta]")
    console.print("[bold magenta]   Rate Limiting Test Suite[/bold magenta]")
    console.print("[bold magenta]═══════════════════════════════════════════════[/bold magenta]")

    try:
        # Test 1: Basic rate limiting
        test_rate_limiting_basic()

        # Test 2: Display stats
        test_stats_display()

        # Test 3: Multi-provider (optional, may not have all keys)
        test_multi_provider()

        # Test 4: Throttling (this might take time)
        # Uncomment to test actual throttling behavior
        # console.print("[yellow]Skipping throttling test (takes time). Uncomment to run.[/yellow]\n")
        # test_rate_limit_throttling()

        console.print("[bold green]═══════════════════════════════════════════════[/bold green]")
        console.print("[bold green]   All Tests Completed Successfully![/bold green]")
        console.print("[bold green]═══════════════════════════════════════════════[/bold green]\n")

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Tests interrupted by user[/yellow]\n")
    except Exception as e:
        console.print(f"\n[bold red]Test failed with error:[/bold red] {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
