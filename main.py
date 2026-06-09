# -*- coding: utf-8 -*-
"""
Self-Healing Ops -- Main Entry Point

Run modes:
  python main.py all [scenario]     -- Single-process mode (recommended for demos)
  python main.py scenario           -- Interactive scenario selection
  python main.py agents             -- Start 3 Agent MCP Servers (distributed mode)
  python main.py run [scenario]     -- Run coordinator (requires agents running)
  python main.py scenarios          -- List all available fault scenarios
"""

import asyncio
import json
import sys
import os
import multiprocessing
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AGENT_CONFIGS, TIMESTAMP_FMT
from infrastructure import InfrastructureSimulator
from coordinator import MCPCoordinator


# )?)? Banner -----)?)?)?)?)?)?)?

def print_banner():
    print("""
~X~~~~~~~~T~T~T~T~[
~U                    SELF-HEALING OPS v2.0                                ~U
~U              Intelligent AIOps Self-Healing System                      ~U
~d~~~~~~~~T~T~T~T~g
~U                                                                        ~U
~U   Architecture:  E-Commerce Microservice Platform                      ~U
~U   Servers:       6 hosts (web, app-?2, db-primary, db-replica, cache)   ~U
~U   Services:      12 microservices (edge/app/data layers)               ~U
~U   Fault Scenarios: 8 realistic production incidents                    ~U
~U                                                                        ~U
~U   Pipeline:      [Monitor] -> [Diagnostic] -> [Repair] -> [Verify]       ~U
~U   Agents:        3 MCP Agents (Tier-1/2/3) with separate API keys      ~U
~U   Protocol:      MCP (Model Context Protocol) over HTTP                ~U
~U   LLM:           MiMo v2.5 Pro (Anthropic-compatible API)              ~U
~U                                                                        ~U
~^~~~~~~~~T~T~T~T~a
""")


# )?)? Scenario Definitions ----)?)?)?)?

SCENARIOS = {
    "1": ("high_cpu",                   "P0 | CPU???? -- ReDoS??????????????"),
    "2": ("memory_leak",                "P0 | ???????) -- Java Heap OOM????????"),
    "3": ("service_crash",              "P0 | ???????? -- ????????????+????????"),
    "4": ("db_slow",                    "P1 | ???????????? -- ?????~??+????????"),
    "5": ("connection_pool_exhaustion", "P1 | ?????????- -- Redis???????)+???????-"),
    "6": ("disk_full",                  "P0 | ?????u -- Binlog 90????????"),
    "7": ("cascading_failure",          "P0 | ???????? -- Redis???u-u???????)-uDB????"),
    "8": ("deployment_regression",      "P1 | ???????? -- N+1??????????????????"),
    "9": ("random",                     "??  | ???u?????-??"),
}


def print_scenarios():
    """Print available fault scenarios."""
    print("\n~X~~~~~~~T~T~[")
    print("~U  AVAILABLE FAULT SCENARIOS                                  ~U")
    print("~d~~~~~~~T~T~g")
    for key, (scenario, desc) in SCENARIOS.items():
        print(f"~U  {key}. {desc:55s} ~U")
    print("~^~~~~~~~T~T~a")


def get_valid_scenario(arg: str) -> str:
    """Validate and return a scenario name."""
    # Check if it's a scenario name directly
    valid_names = [s[0] for s in SCENARIOS.values()]
    if arg in valid_names:
        return arg
    # Check if it's a number
    if arg in SCENARIOS:
        return SCENARIOS[arg][0]
    return "random"


# )?)? Agent Process Launcher ----)?)?)?

def run_agent_process(agent_type: str, infra_state: dict):
    """Run a single agent MCP server in a separate process."""
    import uvicorn
    from infrastructure import InfrastructureSimulator

    infra = InfrastructureSimulator()
    infra.state = infra_state

    if agent_type == "monitor":
        from agents.monitor_agent import create_monitor_agent
        agent = create_monitor_agent(infra)
    elif agent_type == "diagnostic":
        from agents.diagnostic_agent import create_diagnostic_agent
        agent = create_diagnostic_agent(infra)
    elif agent_type == "repair":
        from agents.repair_agent import create_repair_agent
        agent = create_repair_agent(infra)
    else:
        print(f"Unknown agent type: {agent_type}")
        return

    cfg = AGENT_CONFIGS[agent_type]
    uvicorn.run(agent.app, host="127.0.0.1", port=cfg["port"], log_level="warning")


# )?)? Single-Process Mode (Recommended) ---)?)?)?

async def run_single_process_mode(scenario: str):
    """
    Run the full self-healing pipeline in a single process.
    Agents call LLM directly without HTTP -- simpler, faster, no port conflicts.
    """
    from agents.monitor_agent import MonitorAgent
    from agents.diagnostic_agent import DiagnosticAgent
    from agents.repair_agent import RepairAgent

    print("\n" + "=" * 70)
    print("  MODE: Single-process (direct agent calls, no HTTP overhead)")
    print(f"  SCENARIO: {scenario}")
    print("=" * 70)

    infra = InfrastructureSimulator()

    # )?)? Inject Fault ----)?)?)?)?)?
    print(f"\n  [INJECT] Injecting fault scenario: {scenario}")
    actual_scenario = infra.inject_anomaly(scenario)
    print(f"  [INJECT] Actual scenario: {actual_scenario}")
    print(f"  [INJECT] Incident ID: {infra.incident_id}")

    # Show pre-injection health
    health_before = infra.health_check()
    print(f"\n  [HEALTH] Status after fault injection: {health_before['overall'].upper()}")
    for s in health_before.get("unhealthy_servers", []):
        print(f"    [WARN] Server {s['server']} ({s['role']}): {', '.join(s['issues'])}")
    for s in health_before.get("unhealthy_services", []):
        print(f"    [WARN] Service {s['service']} ({s['type']}): {', '.join(s['issues'])}")

    # Show recent logs
    recent_logs = infra.state.logs[-8:]
    print(f"\n  [LOGS] Recent events ({len(recent_logs)} entries):")
    for log in recent_logs:
        level_icon = {"FATAL": "!!!", "ERROR": "ERR", "WARN": "WRN", "INFO": "INF"}.get(log.level, "---")
        print(f"    [{level_icon}] {log.source}: {log.message[:100]}")

    # )?)? Step 1: Monitor Agent ---)?)?)?)?)?)?)?)?
    print("\n" + "-" * 60)
    print("  [Step 1/5] MonitorAgent: Anomaly detection & SLO analysis...")
    print("-" * 60)

    monitor = MonitorAgent(infra)
    monitor_result = await monitor.execute_tool("monitor_check", {})
    print(f"\n  [MONITOR RESULT]:")
    _print_json_summary(monitor_result, max_chars=600)

    # )?)? Step 2: Diagnostic Agent ---)?)?)?)?)?
    print("\n" + "-" * 60)
    print("  [Step 2/5] DiagnosticAgent: Root cause analysis...")
    print("-" * 60)

    diagnostic = DiagnosticAgent(infra)
    diagnostic_result = await diagnostic.execute_tool("diagnose", {"monitor_alert": monitor_result})
    print(f"\n  [DIAGNOSIS RESULT]:")
    _print_json_summary(diagnostic_result, max_chars=800)

    # )?)? Step 3: Repair Plan ---)?)?)?)?)?)?)?)?)?)?
    print("\n" + "-" * 60)
    print("  [Step 3/5] RepairAgent: Creating repair runbook...")
    print("-" * 60)

    repair = RepairAgent(infra)
    plan_result = await repair.execute_tool("create_repair_plan", {"diagnosis": diagnostic_result})
    print(f"\n  [REPAIR PLAN]:")
    _print_json_summary(plan_result, max_chars=600)

    # )?)? Step 4: Execute Repairs ---)?)?)?)?)?)?
    print("\n" + "-" * 60)
    print("  [Step 4/5] RepairAgent: Executing repair steps...")
    print("-" * 60)

    try:
        plan = json.loads(plan_result)
        steps = plan.get("repair_plan", [])
    except (json.JSONDecodeError, TypeError):
        steps = []

    if not steps:
        # Fallback: extract actions from text
        steps = _extract_actions_from_text(plan_result)

    for i, step in enumerate(steps, 1):
        action = step.get("action", "")
        target = step.get("target", "")
        phase = step.get("phase", "resolve")
        risk = step.get("risk", "?")

        phase_icon = {"mitigate": ">>", "resolve": "##", "verify": "OK", "prevent": "--"}.get(phase, "  ")
        print(f"\n  {phase_icon} [{i}/{len(steps)}] {phase.upper()}: {action} -> {target} (risk: {risk})")

        exec_result = await repair.execute_tool("execute_repair", {"action": action, "target": target})
        try:
            r = json.loads(exec_result)
            status = "[OK]" if r.get("success") else "[FAIL]"
            print(f"      Result: {status} - {r.get('message', '')}")
            for act in r.get("actions_taken", []):
                print(f"        -> {act}")
            for side in r.get("side_effects", []):
                print(f"        ** {side}")
        except (json.JSONDecodeError, TypeError):
            print(f"      Result: {str(exec_result)[:200]}")

        # Quick health after each step
        h = infra.health_check()
        print(f"      Health: {h['overall'].upper()} "
              f"(services: {h['healthy_services']}/{h['total_services']})")

    # )?)? Step 5: Verify ----)?)?)?
    print("\n" + "-" * 60)
    print("  [Step 5/5] Post-repair verification...")
    print("-" * 60)

    final_health = infra.health_check()
    print(f"\n  [FINAL HEALTH]")
    print(f"    Overall:   {final_health['overall'].upper()}")
    print(f"    Servers:   {final_health['healthy_servers']}/{final_health['total_servers']}")
    print(f"    Services:  {final_health['healthy_services']}/{final_health['total_services']}")

    if final_health["unhealthy_servers"]:
        for s in final_health["unhealthy_servers"]:
            print(f"    [WARN] Server {s['server']}: {', '.join(s['issues'])}")
    if final_health["unhealthy_services"]:
        for s in final_health["unhealthy_services"]:
            print(f"    [WARN] Service {s['service']}: {', '.join(s['issues'])}")
    if final_health.get("slo_violations"):
        for v in final_health["slo_violations"]:
            print(f"    [SLO] {v['service']}: {v['current_availability']} (target: {v['slo_target']})")
    if not final_health["unhealthy_servers"] and not final_health["unhealthy_services"]:
        print("    ** All components recovered! **")

    print("\n" + "=" * 70)
    print(f"  INCIDENT {infra.incident_id} RESOLVED")
    print(f"  Final Status: {final_health['overall'].upper()}")
    print("=" * 70)


# )?)? Distributed Mode ----)?)?)?)?)?)?)?)?)?

async def run_pipeline(infra: InfrastructureSimulator, scenario: str):
    """Run the pipeline via HTTP calls to distributed agents."""
    coordinator = MCPCoordinator(infra)

    print("\n  [CHECK] Agent health...")
    health = await coordinator.check_health()
    for name, info in health.items():
        status = info.get("status", "UNKNOWN")
        icon = "OK" if status == "ONLINE" else "!!"
        print(f"    [{icon}] {name}: {status}")

    offline = [name for name, info in health.items() if info.get("status") != "ONLINE"]
    if offline:
        print(f"\n  [ERROR] {len(offline)} agent(s) offline: {', '.join(offline)}")
        print("  Run: python main.py agents  (in another terminal)")
        return

    print(f"\n  [INJECT] Fault scenario: {scenario}")
    actual_scenario = infra.inject_anomaly(scenario)
    print(f"  [INJECT] Injected: {actual_scenario}")

    health_before = infra.health_check()
    print(f"\n  [HEALTH] After injection: {health_before['overall'].upper()}")
    for s in health_before.get("unhealthy_servers", []):
        print(f"    [WARN] {s['server']}: {', '.join(s['issues'])}")
    for s in health_before.get("unhealthy_services", []):
        print(f"    [WARN] {s['service']}: {', '.join(s['issues'])}")

    result = await coordinator.run_self_healing_pipeline(verbose=True)
    return result


def start_agents():
    """Start all 3 agent MCP servers as separate processes."""
    infra = InfrastructureSimulator()

    print("\n  Starting Agent MCP Servers...")
    print("-" * 50)

    processes = []
    for agent_type in ["monitor", "diagnostic", "repair"]:
        cfg = AGENT_CONFIGS[agent_type]
        p = multiprocessing.Process(
            target=run_agent_process,
            args=(agent_type, infra.state),
            daemon=True,
        )
        p.start()
        processes.append(p)
        print(f"  [OK] {cfg['name']} started on port {cfg['port']} ({cfg['role']})")
        time.sleep(0.5)

    print(f"\n  All 3 agents running.")
    print(f"  Next: python main.py run [scenario]")
    print(f"  Press Ctrl+C to stop all agents.")
    return processes


# )?)? Utilities -----)?)?)?)?

def _print_json_summary(json_str: str, max_chars: int = 800):
    """Print a summary of JSON output."""
    try:
        data = json.loads(json_str)
        formatted = json.dumps(data, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        formatted = str(json_str)

    if len(formatted) > max_chars:
        for line in formatted[:max_chars].split("\n"):
            print(f"    {line}")
        print(f"    ... ({len(formatted) - max_chars} more chars)")
    else:
        for line in formatted.split("\n"):
            print(f"    {line}")


def _extract_actions_from_text(text: str) -> list[dict]:
    """Fallback: extract repair actions from unstructured LLM output."""
    actions = []
    action_keywords = [
        "restart_service", "rollback_deploy", "kill_process", "clear_cache",
        "scale_up", "cleanup_disk", "fix_config", "add_index",
        "failover_replica", "drain_connections", "circuit_breaker_reset",
    ]
    service_names = [
        "nginx", "api-gateway", "user-service", "order-service",
        "payment-service", "inventory-service", "notification-service",
        "mysql-primary", "mysql-replica", "redis-cluster", "rabbitmq", "elasticsearch",
    ]
    for keyword in action_keywords:
        if keyword in text:
            idx = text.index(keyword)
            context = text[max(0, idx - 50):idx + 100]
            target = ""
            for svc in service_names:
                if svc in context:
                    target = svc
                    break
            actions.append({"action": keyword, "target": target, "phase": "resolve", "risk": "medium"})
    return actions


# )?)? Interactive Scenario Selection ---)?)?)?)?)?)?)?

def select_scenario() -> str:
    print_scenarios()
    choice = input("\n  Select scenario (1-9): ").strip()
    if choice in SCENARIOS:
        return SCENARIOS[choice][0]
    print("  Invalid choice, using random scenario")
    return "random"


# )?)? Main Entry -----)?)?)?

def main():
    print_banner()

    if len(sys.argv) < 2:
        print("  Usage:")
        print("    python main.py all [scenario]     # Single-process mode (recommended)")
        print("    python main.py scenario           # Interactive scenario selection")
        print("    python main.py agents             # Start 3 Agent MCP Servers")
        print("    python main.py run [scenario]     # Run coordinator (agents must be running)")
        print("    python main.py scenarios          # List all fault scenarios")
        print()
        print("  Examples:")
        print("    python main.py all high_cpu")
        print("    python main.py all cascading_failure")
        print("    python main.py all 7              # cascading_failure by number")
        print("    python main.py all deployment_regression")
        print()
        print_scenarios()
        return

    command = sys.argv[1].lower()

    if command == "scenarios":
        print_scenarios()

    elif command == "scenario":
        scenario = select_scenario()
        asyncio.run(run_single_process_mode(scenario))

    elif command == "all":
        arg = sys.argv[2] if len(sys.argv) > 2 else "random"
        scenario = get_valid_scenario(arg)
        asyncio.run(run_single_process_mode(scenario))

    elif command == "agents":
        processes = start_agents()
        try:
            for p in processes:
                p.join()
        except KeyboardInterrupt:
            print("\n  Stopping all agents...")
            for p in processes:
                p.terminate()

    elif command == "run":
        arg = sys.argv[2] if len(sys.argv) > 2 else "random"
        scenario = get_valid_scenario(arg)
        infra = InfrastructureSimulator()
        asyncio.run(run_pipeline(infra, scenario))

    else:
        print(f"  Unknown command: {command}")
        print("  Valid commands: all, scenario, agents, run, scenarios")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()