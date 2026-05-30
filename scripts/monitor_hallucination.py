#!/usr/bin/env python3
"""
Monitor Hallucination Markers in Real-Time

Watches RAG server logs and detects:
- Inference/hallucination markers in responses
- Unsupported service requests
- Fallback triggers
- Performance metrics
"""

import subprocess
import re
import time
import json
from datetime import datetime
from collections import defaultdict

# Hallucination markers to watch
HALLUCINATION_MARKERS = [
    "khoảng", "tầm", "khoảng khoảng",
    "thường", "hay", "có thể", "có khả năng",
    "chắc", "dự tính", "theo tôi", "tôi nghĩ",
    "có lẽ", "hình như", "hình tượng",
    "tùy", "tùy mức độ", "tuỳ vào",
    "sẽ", "có thể sẽ",
    "gần như", "khoảng chừng", "đại loại",
]

UNSUPPORTED_SERVICES = [
    "khóa cửa", "lò nướng", "tủ lạnh",
    "máy giặt", "máy sấy", "bếp", "lò vi sóng"
]

# Statistics
stats = {
    "total_queries": 0,
    "hallucinations": 0,
    "fallbacks": 0,
    "unsupported": 0,
    "avg_latency_ms": 0,
    "queries_with_tools": 0,
}

def extract_metric(line):
    """Extract metrics from log line"""
    # Pattern: trace id=... lat=21873.1ms q='query'
    match = re.search(r"lat=(\d+\.?\d*)ms.*q='([^']*)'", line)
    if match:
        latency = float(match.group(1))
        query = match.group(2)
        return {
            "latency": latency,
            "query": query,
            "timestamp": datetime.now().isoformat()
        }
    return None

def check_hallucination(response_text):
    """Check if response contains hallucination markers"""
    response_lower = response_text.lower()
    found_markers = [m for m in HALLUCINATION_MARKERS if m in response_lower]
    return found_markers

def check_unsupported(query):
    """Check if query asks about unsupported service"""
    query_lower = query.lower()
    for service in UNSUPPORTED_SERVICES:
        if service in query_lower:
            return service
    return None

def parse_log_line(line):
    """Parse relevant information from log line"""
    info = {}

    # Check for trace log
    if "trace id=" in line:
        match = re.search(r"lat=(\d+\.?\d*)ms.*q='([^']*)'", line)
        if match:
            info["latency"] = float(match.group(1))
            info["query"] = match.group(2)
            info["type"] = "trace"

    # Check for fallback
    if "[FALLBACK]" in line:
        match = re.search(r"\[FALLBACK\] Detected: (\w+)", line)
        if match:
            info["fallback_reason"] = match.group(1)
            info["type"] = "fallback"

    # Check for tool call
    if "tool_name=" in line:
        match = re.search(r"tool_name=(\w+)", line)
        if match:
            info["tool"] = match.group(1)
            info["type"] = "tool"

    return info

def display_dashboard(stats, recent_events):
    """Display real-time monitoring dashboard"""
    print("\033[2J\033[H")  # Clear screen
    print("╔════════════════════════════════════════════════════════════════════════════════╗")
    print("║           🤖 FIXAGO RAG - HALLUCINATION MONITORING DASHBOARD                  ║")
    print("╚════════════════════════════════════════════════════════════════════════════════╝")
    print("")

    # Statistics
    print("📊 STATISTICS")
    print("├─ Total Queries:        ", stats["total_queries"])
    print("├─ Hallucinations Detected:", stats["hallucinations"], end="")
    if stats["total_queries"] > 0:
        halluc_rate = (stats["hallucinations"] * 100) // stats["total_queries"]
        print(f" ({halluc_rate}%)")
    else:
        print()
    print("├─ Fallback Triggered:   ", stats["fallbacks"])
    print("├─ Unsupported Requests: ", stats["unsupported"])
    print("├─ Avg Latency:          ", f"{stats['avg_latency_ms']:.0f}ms")
    print("└─ Queries with Tools:   ", stats["queries_with_tools"])
    print("")

    # Recent Events
    print("📋 RECENT EVENTS (Last 10)")
    print("├─────────────────────────────────────────────────────────────────────────────────")
    for i, event in enumerate(recent_events[-10:], 1):
        timestamp = event.get("timestamp", "")
        event_type = event.get("type", "unknown")

        if event_type == "hallucination":
            markers = event.get("markers", [])
            print(f"├ [{i}] 🚨 HALLUCINATION: {markers[0] if markers else 'unknown'}")
            print(f"|     Query: {event.get('query', '')[:50]}...")
        elif event_type == "fallback":
            reason = event.get("reason", "unknown")
            print(f"├ [{i}] 🛑 FALLBACK: {reason}")
        elif event_type == "unsupported":
            service = event.get("service", "unknown")
            print(f"├ [{i}] ⚠️  UNSUPPORTED: {service}")
        elif event_type == "tool_call":
            tool = event.get("tool", "unknown")
            print(f"├ [{i}] 🔧 TOOL CALL: {tool}")
        elif event_type == "query":
            latency = event.get("latency", 0)
            print(f"├ [{i}] ✅ QUERY: {event.get('query', '')[:50]}... ({latency:.0f}ms)")

    print("└─────────────────────────────────────────────────────────────────────────────────")
    print("")

    # Quality Indicators
    print("🎯 QUALITY INDICATORS")
    if stats["total_queries"] > 0:
        halluc_rate = (stats["hallucinations"] * 100) / stats["total_queries"]
        if halluc_rate < 5:
            health = "🟢 EXCELLENT"
        elif halluc_rate < 15:
            health = "🟡 GOOD"
        elif halluc_rate < 30:
            health = "🟠 WARNING"
        else:
            health = "🔴 CRITICAL"
    else:
        health = "⚫ NO DATA"

    print(f"├─ Hallucination Rate: {halluc_rate:.1f}% {health}")
    print(f"├─ System Health: {'✅ NORMAL' if stats['hallucinations'] < 5 else '⚠️ NEEDS ATTENTION'}")
    print(f"└─ Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    # Instructions
    print("💡 CONTROLS")
    print("├─ Press Ctrl+C to stop monitoring")
    print("├─ Check detailed logs: tail -f rag.log")
    print("└─ Test system: python3 scripts/test_agent.py")
    print("")

def monitor_logs():
    """Monitor RAG server logs in real-time"""
    recent_events = []
    latencies = []

    print("🔍 Starting hallucination monitor...")
    print("⏳ Waiting for log data...\n")

    # Tail the log file
    process = subprocess.Popen(
        ["tail", "-f", "rag.log"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    try:
        for line in process.stdout:
            # Parse log line
            info = parse_log_line(line)

            if not info:
                continue

            # Track statistics
            if "query" in info:
                stats["total_queries"] += 1
                query = info.get("query", "")

                # Check for unsupported service
                unsupported_service = check_unsupported(query)
                if unsupported_service:
                    stats["unsupported"] += 1
                    recent_events.append({
                        "type": "unsupported",
                        "service": unsupported_service,
                        "query": query,
                        "timestamp": datetime.now().isoformat()
                    })

            if "latency" in info:
                latencies.append(info["latency"])
                if latencies:
                    stats["avg_latency_ms"] = sum(latencies) / len(latencies)

                recent_events.append({
                    "type": "query",
                    "query": info.get("query", ""),
                    "latency": info["latency"],
                    "timestamp": datetime.now().isoformat()
                })

            if "tool" in info:
                stats["queries_with_tools"] += 1
                recent_events.append({
                    "type": "tool_call",
                    "tool": info["tool"],
                    "timestamp": datetime.now().isoformat()
                })

            if "fallback_reason" in info:
                stats["fallbacks"] += 1
                recent_events.append({
                    "type": "fallback",
                    "reason": info["fallback_reason"],
                    "timestamp": datetime.now().isoformat()
                })

            # Display dashboard every 5 events
            if stats["total_queries"] % 5 == 0 or stats["fallbacks"] > 0:
                display_dashboard(stats, recent_events)

    except KeyboardInterrupt:
        print("\n\n✋ Monitoring stopped by user")
        process.terminate()
        print("\n📊 Final Statistics:")
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    try:
        monitor_logs()
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)
