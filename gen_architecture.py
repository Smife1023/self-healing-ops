# -*- coding: utf-8 -*-
"""Generate Self-Healing Ops architecture diagram using GPT-image-2 via curl."""

import base64
import json
import os
import subprocess

API_KEY = os.getenv("IMAGEGEN_API_KEY", "")
if not API_KEY:
    raise ValueError("IMAGEGEN_API_KEY environment variable is required")
API_URL = os.getenv("IMAGEGEN_API_URL", "https://aihubmix.com/v1/images/generations")
OUTPUT_PATH = "docs/architecture.png"

prompt = (
    "You are a scientific illustration expert. Draw a professional architecture diagram for a "
    "Self-Healing AIOps system. The style should be HAND-DRAWN / SKETCH style on a WHITE background, "
    "like a whiteboard diagram with pen strokes. Flat vector style, no photos/emojis/3D/shadows. "
    "Suitable for a technical README on GitHub.\n\n"
    "=== SYSTEM DESCRIPTION ===\n\n"
    "This is an MCP (Model Context Protocol) Multi-Agent system that automatically detects, "
    "diagnoses, and repairs production infrastructure faults. It simulates a real e-commerce "
    "microservice platform with 6 servers, 12 services, and 3 AI agents.\n\n"
    "=== DIAGRAM SPECIFICATION ===\n\n"
    "The diagram should have TWO main sections arranged TOP-TO-BOTTOM:\n\n"
    "TOP SECTION -- \"E-Commerce Microservice Platform\" "
    "(pale blue background, hand-drawn box with dashed border)\n\n"
    "Show 3 horizontal layers:\n\n"
    "Layer 1 -- \"Edge Layer\" (top):\n"
    "  - \"Nginx (LB)\" box on the left, with an arrow pointing right to\n"
    "  - \"API Gateway (Kong)\" box in the center\n\n"
    "Layer 2 -- \"Application Layer\" (middle):\n"
    "  - 4 boxes side by side: \"user-service\" | \"order-service\" | \"payment-service\" | \"inventory-service\"\n"
    "  - Below them, 2 smaller boxes: \"notification-service\" | \"Elasticsearch\"\n"
    "  - Draw arrows from API Gateway down to the 4 main services\n\n"
    "Layer 3 -- \"Data Layer\" (bottom):\n"
    "  - Left: \"MySQL Primary\" box with a small arrow to \"MySQL Replica\" below it\n"
    "  - Center: \"Redis Cluster\" box\n"
    "  - Right: \"RabbitMQ\" box\n"
    "  - Draw arrows from application services down to data layer\n\n"
    "On the right side, show server labels:\n"
    "  - \"web-lb-01\" (4C) next to Nginx\n"
    "  - \"app-server-01/02\" (16C/32G) next to app layer\n"
    "  - \"db-master-01\" (32C/128G) + \"db-replica-01\" (16C/64G) next to DB\n"
    "  - \"cache-queue-01\" (8C/64G) next to Redis/RabbitMQ\n\n"
    "BOTTOM SECTION -- \"MCP Self-Healing Pipeline\"\n\n"
    "Show 3 agent boxes side by side connected by arrows:\n\n"
    "Box 1 (left, pale green fill):\n"
    "  \"Monitor Agent\" (Tier-1)\n"
    "  Port: :9101\n"
    "  Tools: monitor_check, get_snapshot, check_health, dep_status\n"
    "  Label: \"Detection + SLO Burn-Rate\"\n\n"
    "Arrow pointing right -->\n\n"
    "Box 2 (center, pale yellow fill):\n"
    "  \"Diagnostic Agent\" (Tier-2)\n"
    "  Port: :9102\n"
    "  Tools: diagnose, get_logs, dep_graph, trace_impact\n"
    "  Label: \"Root Cause Analysis + Blast Radius\"\n\n"
    "Arrow pointing right -->\n\n"
    "Box 3 (right, pale red/orange fill):\n"
    "  \"Repair Agent\" (Tier-3)\n"
    "  Port: :9103\n"
    "  Tools: create_plan, execute, verify, rollback\n"
    "  Label: \"Runbook Execution + Rollback\"\n\n"
    "Below the 3 agents, draw a wide box:\n"
    "  \"MCP Coordinator\"\n"
    "  \"Pipeline Orchestration | Incident Timeline | Post-Mortem\"\n"
    "  With arrows from all 3 agents pointing down to it\n\n"
    "Above the 3 agents, draw a large bracket or arrow coming DOWN from the E-Commerce section "
    "with label \"Fault Injection / Monitoring Data\"\n\n"
    "SIDE ANNOTATIONS (right margin):\n"
    "Show a vertical flow on the far right:\n"
    "  Step 1: \"Detect\"\n"
    "  Step 2: \"Diagnose\"\n"
    "  Step 3: \"Plan\"\n"
    "  Step 4: \"Execute\"\n"
    "  Step 5: \"Verify\"\n"
    "Connected by downward arrows\n\n"
    "LEGEND (bottom-left corner):\n"
    "Solid arrow -> Data flow / Dependency\n"
    "Dashed arrow -> Monitoring / Alert flow\n"
    "Colored boxes -> Different service tiers"
)

print(f"Generating image ({len(prompt)} chars prompt)...")

payload = json.dumps({
    "model": "gpt-image-2",
    "prompt": prompt,
    "n": 1,
    "size": "1536x1024",
    "quality": "high",
})

# Write payload to temp file to avoid shell escaping issues
payload_path = "_payload.json"
with open(payload_path, "w", encoding="utf-8") as f:
    f.write(payload)

result = subprocess.run([
    "curl", "-s", "-X", "POST", API_URL,
    "-H", f"Authorization: Bearer {API_KEY}",
    "-H", "Content-Type: application/json",
    "-d", f"@{payload_path}",
], capture_output=True, text=True, timeout=300)

os.remove(payload_path)

if result.returncode != 0:
    print(f"curl failed: {result.stderr}")
    exit(1)

try:
    data = json.loads(result.stdout)
    b64_data = data["data"][0]["b64_json"]
    image_bytes = base64.b64decode(b64_data)
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        f.write(image_bytes)
    print(f"Saved to {OUTPUT_PATH} ({len(image_bytes):,} bytes)")
except (json.JSONDecodeError, KeyError) as e:
    print(f"Error parsing response: {e}")
    print(f"Response: {result.stdout[:500]}")