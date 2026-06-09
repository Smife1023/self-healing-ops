# -*- coding: utf-8 -*-
"""
Infrastructure Simulator -- Realistic production environment emulation.

Simulates a microservice e-commerce platform with:
  - 5 servers (web cluster, app cluster, DB primary/replica, cache/queue)
  - 12 services (Nginx, API Gateway, user/order/payment/inventory/notification services,
    MySQL primary + replica, Redis, RabbitMQ, Elasticsearch, Prometheus-exporter)
  - Service dependency graph (cascading failure modeling)
  - 8 fault scenarios with realistic log chains and metric degradation patterns
  - Incident timeline with before/during/after snapshots
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from config import TIMESTAMP_FMT


# ~~~~~~~~T~T~T~T~T~T~T~T~T
#  Data Models
# ~~~~~~~~T~T~T~T~T~T~T~T~T

@dataclass
class ServerMetrics:
    """OS-level metrics for a single host (collected every 15s via node_exporter)."""
    hostname: str
    role: str                              # e.g. "web", "app", "db-primary", "cache"
    cpu_cores: int = 8
    cpu_usage: float = 30.0               # %
    memory_total_gb: float = 32.0
    memory_usage: float = 40.0            # %
    disk_total_gb: float = 500.0
    disk_usage: float = 50.0              # %
    network_rx_mbps: float = 50.0
    network_tx_mbps: float = 30.0
    load_avg_1m: float = 1.5
    load_avg_5m: float = 1.2
    load_avg_15m: float = 1.0
    open_files: int = 200
    tcp_connections: int = 150
    tcp_time_wait: int = 30
    iowait_pct: float = 2.0
    uptime_hours: float = 720.0


@dataclass
class ServiceStatus:
    """Application-level metrics for a single microservice."""
    name: str
    service_type: str                     # "web", "app", "database", "cache", "queue", "search"
    status: str = "running"               # running / degraded / down
    port: int = 8080
    pid: int = 0
    host: str = ""                        # which server it runs on
    replicas: int = 1
    response_time_p50_ms: float = 30.0
    response_time_p99_ms: float = 120.0
    error_rate: float = 0.005             # 0.5%
    request_count_1m: int = 500           # requests per minute
    restart_count: int = 0
    last_restart: Optional[str] = None
    memory_rss_mb: float = 256.0          # resident memory
    thread_count: int = 50
    connection_pool_size: int = 50
    connection_pool_active: int = 20
    heap_usage_pct: float = 45.0          # for JVM-based services
    gc_pause_ms: float = 15.0
    circuit_breaker_state: str = "closed"  # closed / open / half-open


@dataclass
class LogEntry:
    timestamp: str
    level: str                            # TRACE / DEBUG / INFO / WARN / ERROR / FATAL
    source: str
    message: str
    trace_id: str = ""
    span_id: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class DependencyEdge:
    """Represents a runtime dependency between two services."""
    upstream: str      # caller
    downstream: str    # callee
    protocol: str      # "http", "grpc", "tcp", "mysql", "redis"
    timeout_ms: int = 3000
    retry_count: int = 2
    critical: bool = True   # if True, downstream failure propagates upstream


@dataclass
class IncidentEvent:
    timestamp: str
    event_type: str          # ANOMALY_DETECTED / DIAGNOSIS / REPAIR_STARTED / REPAIR_COMPLETED / VERIFIED
    agent: str               # which agent generated this
    summary: str
    details: dict = field(default_factory=dict)


@dataclass
class InfraState:
    servers: dict = field(default_factory=dict)
    services: dict = field(default_factory=dict)
    dependencies: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    incidents: list = field(default_factory=list)
    events: list = field(default_factory=list)


# ~~~~~~~~T~T~T~T~T~T~T~T~T
#  Infrastructure Simulator
# ~~~~~~~~T~T~T~T~T~T~T~T~T

class InfrastructureSimulator:
    """
    Simulates a production e-commerce platform infrastructure.

    Architecture:
        [Load Balancer / Nginx]
              )?
        [API Gateway (Kong)]
          --
          ~?   ~?       ~?          ~?
      [user-svc] [order-svc] [payment-svc] [inventory-svc]
          )?        )?    )?         )?
          ~?        ~?    ~?         ~?
      [MySQL-Primary] [Redis-Cluster] [RabbitMQ]
          )?
          ~?
      [MySQL-Replica]
          )?
      [notification-svc] -? [RabbitMQ]
      [Elasticsearch] -? [order-svc, user-svc logs]
    """

    def __init__(self):
        self.state = InfraState()
        self.anomaly_injected = False
        self.incident_id: Optional[str] = None
        self._init_infrastructure()

    # )?)? Initialization ----)?)?)?)?)?)?)?

    def _init_infrastructure(self):
        self._init_servers()
        self._init_services()
        self._init_dependencies()
        self._init_baseline_logs()

    def _init_servers(self):
        self.state.servers = {
            "web-lb-01": ServerMetrics(
                hostname="web-lb-01", role="load-balancer", cpu_cores=4,
                cpu_usage=15.0, memory_usage=25.0, disk_usage=20.0,
                network_rx_mbps=200.0, network_tx_mbps=180.0,
                load_avg_1m=0.8, load_avg_5m=0.7, load_avg_15m=0.6,
                open_files=100, tcp_connections=2000, tcp_time_wait=50,
                iowait_pct=0.5, uptime_hours=2160.0,
            ),
            "app-server-01": ServerMetrics(
                hostname="app-server-01", role="application", cpu_cores=16,
                cpu_usage=45.0, memory_usage=62.0, disk_usage=35.0,
                network_rx_mbps=80.0, network_tx_mbps=60.0,
                load_avg_1m=3.2, load_avg_5m=2.8, load_avg_15m=2.5,
                open_files=350, tcp_connections=800, tcp_time_wait=120,
                iowait_pct=3.0, uptime_hours=720.0,
            ),
            "app-server-02": ServerMetrics(
                hostname="app-server-02", role="application", cpu_cores=16,
                cpu_usage=42.0, memory_usage=58.0, disk_usage=32.0,
                network_rx_mbps=75.0, network_tx_mbps=55.0,
                load_avg_1m=2.9, load_avg_5m=2.6, load_avg_15m=2.3,
                open_files=320, tcp_connections=750, tcp_time_wait=100,
                iowait_pct=2.5, uptime_hours=720.0,
            ),
            "db-master-01": ServerMetrics(
                hostname="db-master-01", role="db-primary", cpu_cores=32,
                cpu_usage=55.0, memory_usage=78.0, disk_usage=72.0,
                network_rx_mbps=40.0, network_tx_mbps=60.0,
                load_avg_1m=5.0, load_avg_5m=4.5, load_avg_15m=4.0,
                open_files=800, tcp_connections=500, tcp_time_wait=20,
                iowait_pct=8.0, uptime_hours=4320.0,
                memory_total_gb=128.0, disk_total_gb=2000.0,
            ),
            "db-replica-01": ServerMetrics(
                hostname="db-replica-01", role="db-replica", cpu_cores=16,
                cpu_usage=35.0, memory_usage=65.0, disk_usage=68.0,
                network_rx_mbps=30.0, network_tx_mbps=20.0,
                load_avg_1m=2.5, load_avg_5m=2.3, load_avg_15m=2.0,
                open_files=600, tcp_connections=300, tcp_time_wait=15,
                iowait_pct=5.0, uptime_hours=4320.0,
                memory_total_gb=64.0, disk_total_gb=2000.0,
            ),
            "cache-queue-01": ServerMetrics(
                hostname="cache-queue-01", role="cache-and-queue", cpu_cores=8,
                cpu_usage=28.0, memory_usage=72.0, disk_usage=25.0,
                network_rx_mbps=150.0, network_tx_mbps=140.0,
                load_avg_1m=1.8, load_avg_5m=1.6, load_avg_15m=1.4,
                open_files=150, tcp_connections=3000, tcp_time_wait=80,
                iowait_pct=1.0, uptime_hours=1440.0,
                memory_total_gb=64.0,
            ),
        }

    def _init_services(self):
        self.state.services = {
            # )?)? Edge Layer ---)?)?)?)?)?)?)?)?)?)?)?
            "nginx": ServiceStatus(
                name="nginx", service_type="web", port=80, pid=1234,
                host="web-lb-01", replicas=1,
                response_time_p50_ms=5, response_time_p99_ms=15,
                error_rate=0.001, request_count_1m=12000,
                memory_rss_mb=64, thread_count=4,
            ),
            "api-gateway": ServiceStatus(
                name="api-gateway", service_type="web", port=8080, pid=2345,
                host="app-server-01", replicas=2,
                response_time_p50_ms=25, response_time_p99_ms=80,
                error_rate=0.008, request_count_1m=8000,
                memory_rss_mb=512, thread_count=100,
                connection_pool_size=200, connection_pool_active=80,
            ),
            # )?)? Application Layer ---)?)?)?)?
            "user-service": ServiceStatus(
                name="user-service", service_type="app", port=8081, pid=3456,
                host="app-server-01", replicas=2,
                response_time_p50_ms=45, response_time_p99_ms=150,
                error_rate=0.005, request_count_1m=3000,
                memory_rss_mb=384, thread_count=60,
                connection_pool_size=50, connection_pool_active=15,
                heap_usage_pct=42.0, gc_pause_ms=12.0,
            ),
            "order-service": ServiceStatus(
                name="order-service", service_type="app", port=8082, pid=4567,
                host="app-server-01", replicas=2,
                response_time_p50_ms=80, response_time_p99_ms=250,
                error_rate=0.01, request_count_1m=1500,
                memory_rss_mb=512, thread_count=80,
                connection_pool_size=80, connection_pool_active=35,
                heap_usage_pct=55.0, gc_pause_ms=20.0,
            ),
            "payment-service": ServiceStatus(
                name="payment-service", service_type="app", port=8083, pid=5100,
                host="app-server-02", replicas=2,
                response_time_p50_ms=120, response_time_p99_ms=400,
                error_rate=0.002, request_count_1m=800,
                memory_rss_mb=384, thread_count=40,
                connection_pool_size=30, connection_pool_active=10,
                heap_usage_pct=38.0, gc_pause_ms=10.0,
            ),
            "inventory-service": ServiceStatus(
                name="inventory-service", service_type="app", port=8084, pid=5200,
                host="app-server-02", replicas=2,
                response_time_p50_ms=60, response_time_p99_ms=180,
                error_rate=0.008, request_count_1m=2000,
                memory_rss_mb=320, thread_count=55,
                connection_pool_size=60, connection_pool_active=25,
                heap_usage_pct=48.0, gc_pause_ms=15.0,
            ),
            "notification-service": ServiceStatus(
                name="notification-service", service_type="app", port=8085, pid=5300,
                host="app-server-02", replicas=1,
                response_time_p50_ms=30, response_time_p99_ms=100,
                error_rate=0.005, request_count_1m=500,
                memory_rss_mb=192, thread_count=20,
                connection_pool_size=20, connection_pool_active=5,
                heap_usage_pct=30.0, gc_pause_ms=8.0,
            ),
            # )?)? Data Layer ---)?)?)?)?)?)?)?)?)?)?)?
            "mysql-primary": ServiceStatus(
                name="mysql-primary", service_type="database", port=3306, pid=6000,
                host="db-master-01", replicas=1,
                response_time_p50_ms=8, response_time_p99_ms=45,
                error_rate=0.0005, request_count_1m=25000,
                memory_rss_mb=4096, thread_count=200,
                connection_pool_size=500, connection_pool_active=180,
            ),
            "mysql-replica": ServiceStatus(
                name="mysql-replica", service_type="database", port=3307, pid=6100,
                host="db-replica-01", replicas=1,
                response_time_p50_ms=10, response_time_p99_ms=55,
                error_rate=0.0005, request_count_1m=15000,
                memory_rss_mb=2048, thread_count=150,
                connection_pool_size=300, connection_pool_active=100,
            ),
            "redis-cluster": ServiceStatus(
                name="redis-cluster", service_type="cache", port=6379, pid=7000,
                host="cache-queue-01", replicas=3,
                response_time_p50_ms=0.8, response_time_p99_ms=3.0,
                error_rate=0.0, request_count_1m=80000,
                memory_rss_mb=8192, thread_count=6,
                connection_pool_size=10000, connection_pool_active=3500,
            ),
            "rabbitmq": ServiceStatus(
                name="rabbitmq", service_type="queue", port=5672, pid=8000,
                host="cache-queue-01", replicas=1,
                response_time_p50_ms=2, response_time_p99_ms=8,
                error_rate=0.0, request_count_1m=10000,
                memory_rss_mb=1024, thread_count=120,
            ),
            "elasticsearch": ServiceStatus(
                name="elasticsearch", service_type="search", port=9200, pid=9000,
                host="db-replica-01", replicas=1,
                response_time_p50_ms=15, response_time_p99_ms=80,
                error_rate=0.002, request_count_1m=5000,
                memory_rss_mb=4096, thread_count=40,
                heap_usage_pct=65.0, gc_pause_ms=50.0,
            ),
        }

    def _init_dependencies(self):
        """Define the service dependency graph."""
        self.state.dependencies = [
            DependencyEdge("nginx", "api-gateway", "http", timeout_ms=5000),
            DependencyEdge("api-gateway", "user-service", "grpc", timeout_ms=3000),
            DependencyEdge("api-gateway", "order-service", "grpc", timeout_ms=3000),
            DependencyEdge("api-gateway", "payment-service", "grpc", timeout_ms=5000),
            DependencyEdge("api-gateway", "inventory-service", "grpc", timeout_ms=3000),
            DependencyEdge("user-service", "mysql-primary", "mysql", timeout_ms=2000),
            DependencyEdge("user-service", "redis-cluster", "redis", timeout_ms=500),
            DependencyEdge("order-service", "mysql-primary", "mysql", timeout_ms=2000),
            DependencyEdge("order-service", "redis-cluster", "redis", timeout_ms=500),
            DependencyEdge("order-service", "inventory-service", "grpc", timeout_ms=2000),
            DependencyEdge("order-service", "rabbitmq", "amqp", timeout_ms=1000),
            DependencyEdge("payment-service", "mysql-primary", "mysql", timeout_ms=2000),
            DependencyEdge("payment-service", "order-service", "grpc", timeout_ms=3000),
            DependencyEdge("inventory-service", "mysql-primary", "mysql", timeout_ms=2000),
            DependencyEdge("inventory-service", "redis-cluster", "redis", timeout_ms=500),
            DependencyEdge("notification-service", "rabbitmq", "amqp", timeout_ms=1000),
            DependencyEdge("mysql-primary", "mysql-replica", "mysql-replication", timeout_ms=0, critical=False),
        ]

    def _init_baseline_logs(self):
        now = datetime.now()
        base_logs = [
            (0,  "INFO",  "system",           "Infrastructure initialized -- all services healthy"),
            (0,  "INFO",  "nginx",            "nginx/1.24.0 starting on :80, worker_processes=4"),
            (0,  "INFO",  "api-gateway",      "Kong 3.4 listening on :8080, plugins: rate-limit, jwt, cors"),
            (1,  "INFO",  "user-service",     "user-service v2.3.1 started, db_pool=50, cache_ttl=300s"),
            (1,  "INFO",  "order-service",    "order-service v1.8.0 started, mq_connected=true"),
            (2,  "INFO",  "payment-service",  "payment-service v3.1.0 started, pci_compliance_mode=strict"),
            (2,  "INFO",  "inventory-service","inventory-service v1.5.2 started, warehouse_count=3"),
            (3,  "INFO",  "mysql-primary",    "MySQL 8.0.35 started, innodb_buffer_pool=64G, binlog=ROW"),
            (3,  "INFO",  "redis-cluster",    "Redis 7.2.3 started, maxmemory=16G, policy=allkeys-lru"),
            (4,  "INFO",  "rabbitmq",         "RabbitMQ 3.12.0 started, Erlang 26.1"),
            (5,  "INFO",  "elasticsearch",    "Elasticsearch 8.11.0 started, heap=4G, cluster=green"),
            (10, "INFO",  "nginx",            "Health check: all upstreams healthy"),
        ]
        for offset, level, source, msg in base_logs:
            ts = (now + timedelta(seconds=offset * 5)).strftime(TIMESTAMP_FMT)
            self.state.logs.append(LogEntry(ts, level, source, msg))

    # )?)? Fault Injection ----)?)?)?)?)?

    def inject_anomaly(self, scenario: str = "random") -> str:
        self.anomaly_injected = True
        self.incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().strftime(TIMESTAMP_FMT)

        scenarios = {
            "high_cpu":                   self._inject_high_cpu,
            "memory_leak":                self._inject_memory_leak,
            "service_crash":              self._inject_service_crash,
            "db_slow":                    self._inject_db_slow,
            "connection_pool_exhaustion": self._inject_connection_exhaustion,
            "disk_full":                  self._inject_disk_full,
            "cascading_failure":          self._inject_cascading_failure,
            "deployment_regression":      self._inject_deployment_regression,
        }

        if scenario == "random":
            scenario = random.choice(list(scenarios.keys()))

        scenario_name, severity = scenarios[scenario](now)

        self.state.events.append(IncidentEvent(
            timestamp=now, event_type="ANOMALY_DETECTED", agent="system",
            summary=f"[{self.incident_id}] {scenario_name}",
            details={"scenario": scenario, "severity": severity},
        ))
        return scenario

    def _inject_high_cpu(self, now: str) -> tuple:
        """
        Scenario: A background cron job in api-gateway triggers an infinite regex
        (ReDoS) on user-supplied input, pegging CPU at 100% on app-server-01.
        """
        srv = self.state.servers["app-server-01"]
        srv.cpu_usage = 98.3
        srv.load_avg_1m = 28.5
        srv.load_avg_5m = 18.2
        srv.load_avg_15m = 12.0
        srv.open_files = 4200
        srv.iowait_pct = 1.2

        gw = self.state.services["api-gateway"]
        gw.response_time_p50_ms = 3200
        gw.response_time_p99_ms = 8500
        gw.error_rate = 0.18
        gw.request_count_1m = 850  # most requests timing out
        gw.thread_count = 200      # thread pool exhausted

        us = self.state.services["user-service"]
        us.response_time_p50_ms = 2800
        us.response_time_p99_ms = 7000
        us.error_rate = 0.12

        self.state.logs.extend([
            LogEntry(now, "WARN",  "app-server-01",   "CPU usage spike: 98.3% (15m avg: 12.0) -- threshold: 90%"),
            LogEntry(now, "ERROR", "api-gateway",      "Request timeout after 5000ms: GET /api/v2/users/search?q=aaaaaaaaaaa..."),
            LogEntry(now, "ERROR", "api-gateway",      "Thread pool exhausted: 200/200 active, 1243 queued"),
            LogEntry(now, "WARN",  "api-gateway",      "Latency p99 breach: 8500ms > 2000ms (SLO: 99.9% < 500ms)"),
            LogEntry(now, "WARN",  "app-server-01",    "Load average critical: 28.5 (cores: 16, ratio: 1.78)"),
            LogEntry(now, "ERROR", "nginx",            "upstream timed out (110: Connection timed out) while reading response header"),
            LogEntry(now, "ERROR", "api-gateway",      "Error rate breach: 18% (5xx) -- SLO burn rate: 36x"),
            LogEntry(now, "WARN",  "user-service",     "Upstream api-gateway latency propagation: p99 7000ms"),
            LogEntry(now, "INFO",  "app-server-01",    "Process 2345 (api-gateway) CPU: 987% across 10 threads -- suspect ReDoS"),
        ])
        return ("ReDoS infinite regex in api-gateway cron job -- CPU 98.3%, "
                "SLO burn rate 36x", "P0_critical")

    def _inject_memory_leak(self, now: str) -> tuple:
        """
        Scenario: order-service has a Java heap leak in a caching HashMap
        that grows unbounded. OOM Killer starts killing processes.
        """
        srv = self.state.servers["app-server-01"]
        srv.memory_usage = 96.8
        srv.swap_usage = 85.0 if hasattr(srv, 'swap_usage') else 85.0

        osvc = self.state.services["order-service"]
        osvc.status = "degraded"
        osvc.memory_rss_mb = 2800  # normal: 512MB
        osvc.heap_usage_pct = 97.0
        osvc.gc_pause_ms = 4500    # full GC pauses
        osvc.response_time_p50_ms = 4200
        osvc.response_time_p99_ms = 12000
        osvc.error_rate = 0.22
        osvc.restart_count = 4
        osvc.last_restart = now

        self.state.logs.extend([
            LogEntry(now, "WARN",  "app-server-01",    "Memory usage critical: 96.8% (31GB/32GB), swap: 85%"),
            LogEntry(now, "ERROR", "order-service",    "java.lang.OutOfMemoryError: Java heap space -- GC overhead limit exceeded"),
            LogEntry(now, "ERROR", "order-service",    "Full GC pause: 4500ms (threshold: 200ms) -- 20x breach"),
            LogEntry(now, "FATAL", "order-service",    "OOM killer triggered, PID 4567 killed (RSS: 2800MB)"),
            LogEntry(now, "WARN",  "order-service",    "Restarting... (restart #4, previous restarts at 14:01, 14:08, 14:15)"),
            LogEntry(now, "ERROR", "api-gateway",      "order-service connection refused -- circuit breaker OPEN (threshold: 5 failures in 30s)"),
            LogEntry(now, "WARN",  "app-server-01",    "cgroup memory.pressure: some=65.2% full=42.8%"),
            LogEntry(now, "ERROR", "order-service",    "Heap dump triggered: /tmp/order-service-heap-20240101.hprof (2.1GB)"),
            LogEntry(now, "WARN",  "rabbitmq",         "Queue order.created depth: 12,450 messages (threshold: 1000) -- consumer down"),
        ])
        return ("Java heap leak in order-service -- OOM kills, 4 restarts, "
                "heap dump captured", "P0_critical")

    def _inject_service_crash(self, now: str) -> tuple:
        """
        Scenario: payment-service crashes during a deploy due to a missing
        config key (PAYMENT_GATEWAY_SECRET). The new version 3.2.0 has a
        breaking change that wasn't caught in staging.
        """
        psvc = self.state.services["payment-service"]
        psvc.status = "down"
        psvc.error_rate = 1.0
        psvc.response_time_p50_ms = 0
        psvc.response_time_p99_ms = 0
        psvc.restart_count = 3
        psvc.last_restart = now

        gw = self.state.services["api-gateway"]
        gw.error_rate = 0.25
        gw.circuit_breaker_state = "open"

        self.state.logs.extend([
            LogEntry(now, "FATAL", "payment-service",  "Service crashed: KeyError: 'PAYMENT_GATEWAY_SECRET'"),
            LogEntry(now, "FATAL", "payment-service",  "Exit code 1 -- config validation failed at startup"),
            LogEntry(now, "ERROR", "payment-service",  "Deployment v3.2.0 failed, attempting rollback to v3.1.0..."),
            LogEntry(now, "ERROR", "payment-service",  "Rollback failed: old container image expired from registry"),
            LogEntry(now, "ERROR", "api-gateway",      "payment-service unreachable -- returning 503 Service Unavailable"),
            LogEntry(now, "ERROR", "api-gateway",      "Circuit breaker OPEN for payment-service (failures: 12/30s)"),
            LogEntry(now, "ERROR", "nginx",            "upstream payment-service: connection refused (111)"),
            LogEntry(now, "WARN",  "order-service",    "Cannot reach payment-service -- payment requests queued"),
            LogEntry(now, "ERROR", "payment-service",  "Restart attempt #3 failed -- same config error"),
        ])
        return ("payment-service crash on deploy -- missing config key, "
                "rollback failed", "P0_critical")

    def _inject_db_slow(self, now: str) -> tuple:
        """
        Scenario: A developer pushed a full-table scan query without index.
        Combined with high write load, InnoDB row lock contention spikes.
        """
        db = self.state.servers["db-master-01"]
        db.cpu_usage = 94.0
        db.iowait_pct = 62.0
        db.disk_usage = 85.0
        db.load_avg_1m = 22.0

        mysql = self.state.services["mysql-primary"]
        mysql.response_time_p50_ms = 3500
        mysql.response_time_p99_ms = 15000
        mysql.error_rate = 0.08
        mysql.thread_count = 450

        order_svc = self.state.services["order-service"]
        order_svc.response_time_p50_ms = 6000
        order_svc.error_rate = 0.12

        user_svc = self.state.services["user-service"]
        user_svc.response_time_p50_ms = 4500
        user_svc.error_rate = 0.06

        self.state.logs.extend([
            LogEntry(now, "ERROR", "mysql-primary",    "Slow query: 15.2s -- SELECT * FROM orders WHERE created_at > '2024-01-01' AND status='pending' (no index on created_at+status)"),
            LogEntry(now, "WARN",  "mysql-primary",    "InnoDB row lock waits: 847 active (threshold: 50), avg wait: 3.2s"),
            LogEntry(now, "ERROR", "mysql-primary",    "Lock wait timeout exceeded: 50s -- transaction rolled back"),
            LogEntry(now, "WARN",  "db-master-01",     "Disk I/O wait: 62% -- iostat: await=45ms, %util=98%"),
            LogEntry(now, "WARN",  "mysql-primary",    "InnoDB buffer pool hit ratio: 45% (critical threshold: 95%)"),
            LogEntry(now, "ERROR", "order-service",    "Query timeout (2000ms): SELECT * FROM orders WHERE user_id=..."),
            LogEntry(now, "WARN",  "user-service",     "DB connection pool: 50/50 active, 120 waiting -- pool exhausted"),
            LogEntry(now, "WARN",  "mysql-primary",    "Replication lag: 45s (threshold: 10s) -- replica falling behind"),
            LogEntry(now, "ERROR", "api-gateway",      "5xx rate spike: 8% -- correlated with mysql latency"),
        ])
        return ("Full-table scan causing InnoDB row lock contention -- "
                "replication lag 45s", "P1_high")

    def _inject_connection_exhaustion(self, now: str) -> tuple:
        """
        Scenario: Redis maxclients reached due to a connection leak in
        user-service (connections not returned to pool after timeout).
        """
        cache_srv = self.state.servers["cache-queue-01"]
        cache_srv.tcp_connections = 10000
        cache_srv.memory_usage = 88.0

        redis = self.state.services["redis-cluster"]
        redis.response_time_p50_ms = 120
        redis.response_time_p99_ms = 800
        redis.error_rate = 0.05
        redis.connection_pool_active = 9950  # max: 10000

        gw = self.state.services["api-gateway"]
        gw.error_rate = 0.15
        gw.response_time_p99_ms = 3000

        app_srv = self.state.servers["app-server-01"]
        app_srv.tcp_connections = 6500

        self.state.logs.extend([
            LogEntry(now, "ERROR", "redis-cluster",    "ERR max number of clients reached: 10000 (maxclients=10000)"),
            LogEntry(now, "ERROR", "user-service",     "Redis connection error: ETIMEDOUT after 500ms"),
            LogEntry(now, "WARN",  "cache-queue-01",   "TCP connections: 10000 -- system file descriptor limit approaching"),
            LogEntry(now, "ERROR", "api-gateway",      "Request latency spike: 50% of requests > 2000ms"),
            LogEntry(now, "WARN",  "user-service",     "Connection pool leak detected: 480 active, 0 idle (pool_size=50) -- suspected unclosed connections"),
            LogEntry(now, "ERROR", "order-service",    "Redis timeout: cache miss, falling back to DB -- query spike"),
            LogEntry(now, "WARN",  "app-server-01",    "TCP TIME_WAIT: 3200 sockets -- ephemeral port exhaustion risk"),
            LogEntry(now, "WARN",  "notification-service", "RabbitMQ connection delayed: 2.5s (normally <5ms)"),
        ])
        return ("Redis connection pool leak -- maxclients 10000 reached, "
                "ephemeral port exhaustion", "P1_high")

    def _inject_disk_full(self, now: str) -> tuple:
        """
        Scenario: MySQL binary logs accumulated for 90 days without rotation.
        Slow query log grew to 50GB. Disk hits 98.5%.
        """
        db = self.state.servers["db-master-01"]
        db.disk_usage = 98.5

        mysql = self.state.services["mysql-primary"]
        mysql.status = "degraded"
        mysql.error_rate = 0.15
        mysql.response_time_p99_ms = 8000

        replica = self.state.services["mysql-replica"]
        replica.status = "degraded"

        self.state.logs.extend([
            LogEntry(now, "FATAL", "db-master-01",     "Disk usage: 98.5% (1970GB/2000GB) -- CRITICAL"),
            LogEntry(now, "ERROR", "mysql-primary",    "Cannot write to binary log: Error writing file '/var/log/mysql/binlog.000489' (Errcode: 28 - No space left on device)"),
            LogEntry(now, "ERROR", "mysql-primary",    "Transaction rolled back: disk full -- INSERT INTO orders ..."),
            LogEntry(now, "WARN",  "db-master-01",     "Large files: /var/log/mysql/slow.log (50GB), /var/lib/mysql/binlog.* (890GB, 90 days unrotated)"),
            LogEntry(now, "ERROR", "mysql-primary",    "InnoDB: Unable to extend tablespace './ecommerce/orders.ibd' -- write failed"),
            LogEntry(now, "ERROR", "mysql-replica",    "Replication stopped: relay log write failure -- disk full on master"),
            LogEntry(now, "WARN",  "order-service",    "MySQL write failures detected -- switching to read-only mode"),
            LogEntry(now, "ERROR", "payment-service",  "Cannot persist transaction: COMMIT failed -- disk full"),
        ])
        return ("MySQL disk full -- binlog rotation misconfigured for 90 days, "
                "write path blocked", "P0_critical")

    def _inject_cascading_failure(self, now: str) -> tuple:
        """
        Scenario: Redis cluster goes down -> cache miss storm -> DB overload
        -> all services slow -> circuit breakers trip -> platform-wide outage.
        Demonstrates cascading failure through the dependency graph.
        """
        redis = self.state.services["redis-cluster"]
        redis.status = "down"
        redis.error_rate = 1.0
        redis.response_time_p50_ms = 0
        redis.restart_count = 2

        mysql = self.state.services["mysql-primary"]
        mysql.response_time_p50_ms = 2500
        mysql.response_time_p99_ms = 12000
        mysql.error_rate = 0.10
        mysql.request_count_1m = 65000  # normally 25000, cache miss storm

        db = self.state.servers["db-master-01"]
        db.cpu_usage = 96.0
        db.iowait_pct = 45.0
        db.load_avg_1m = 35.0

        for svc_name in ["user-service", "order-service", "inventory-service"]:
            svc = self.state.services[svc_name]
            svc.response_time_p99_ms = 8000
            svc.error_rate = 0.20
            svc.circuit_breaker_state = "open"

        gw = self.state.services["api-gateway"]
        gw.error_rate = 0.35
        gw.circuit_breaker_state = "open"

        nginx = self.state.services["nginx"]
        nginx.error_rate = 0.30

        self.state.logs.extend([
            LogEntry(now, "FATAL", "redis-cluster",    "Redis cluster node failed: CLUSTERDOWN The cluster is down"),
            LogEntry(now, "ERROR", "user-service",     "Redis unavailable: ENOTFOUND -- cache miss, fallback to DB"),
            LogEntry(now, "ERROR", "order-service",    "Redis unavailable: ENOTFOUND -- cache miss, fallback to DB"),
            LogEntry(now, "WARN",  "mysql-primary",    "Connection surge: 65000 req/min (normal: 25000) -- cache miss storm"),
            LogEntry(now, "ERROR", "mysql-primary",    "Thread pool saturated: 450/500 connections active"),
            LogEntry(now, "WARN",  "db-master-01",     "CPU 96%, load 35.0 -- system under extreme pressure"),
            LogEntry(now, "ERROR", "api-gateway",      "Circuit breaker OPEN: user-service (failures: 8/10s)"),
            LogEntry(now, "ERROR", "api-gateway",      "Circuit breaker OPEN: order-service (failures: 12/10s)"),
            LogEntry(now, "ERROR", "nginx",            "5xx rate: 30% -- platform-wide degradation"),
            LogEntry(now, "FATAL", "system",           "CASCADING FAILURE: Redis down -> cache miss storm -> DB overload -> all services degraded"),
        ])
        return ("Cascading failure: Redis down -> cache miss storm -> "
                "DB overload -> platform-wide outage", "P0_critical")

    def _inject_deployment_regression(self, now: str) -> tuple:
        """
        Scenario: inventory-service v1.6.0 introduced an N+1 query bug
        that only manifests under load. Gradual degradation after deploy.
        """
        inv = self.state.services["inventory-service"]
        inv.response_time_p50_ms = 800
        inv.response_time_p99_ms = 5000
        inv.error_rate = 0.08
        inv.heap_usage_pct = 78.0
        inv.gc_pause_ms = 180

        mysql = self.state.services["mysql-primary"]
        mysql.response_time_p50_ms = 450
        mysql.response_time_p99_ms = 2000
        mysql.request_count_1m = 45000  # query spike from N+1

        order = self.state.services["order-service"]
        order.response_time_p50_ms = 1200
        order.error_rate = 0.06

        self.state.logs.extend([
            LogEntry(now, "INFO",  "inventory-service", "Deployment v1.6.0 completed at 14:00 -- rolling update 2 pods"),
            LogEntry(now, "WARN",  "inventory-service", "Response time degradation: p50 800ms (normally 60ms), p99 5000ms"),
            LogEntry(now, "WARN",  "mysql-primary",     "Query count spike: 45000/min (normally 25000) -- suspected N+1 query"),
            LogEntry(now, "ERROR", "inventory-service", "N+1 query detected: getProductStock() executed 847 queries per request (batch_size=1)"),
            LogEntry(now, "WARN",  "inventory-service", "GC pause increase: 180ms (normally 15ms) -- heap pressure from query objects"),
            LogEntry(now, "ERROR", "order-service",     "inventory-service latency: 5000ms timeout on check_stock()"),
            LogEntry(now, "WARN",  "order-service",     "Order creation success rate dropped: 94% (normally 99.8%)"),
            LogEntry(now, "INFO",  "inventory-service", "Correlation: latency spike started 2min after v1.6.0 deploy"),
        ])
        return ("inventory-service v1.6.0 N+1 query regression -- "
                "847 queries/request, gradual degradation", "P1_high")

    # )?)? Query Methods ----)?)?)?)?)?)?)?

    def get_monitor_snapshot(self) -> dict:
        """Return a complete monitoring snapshot (as collected by Prometheus/Grafana)."""
        return {
            "snapshot_id": f"SNAP-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now().strftime(TIMESTAMP_FMT),
            "collection_interval": "15s",
            "data_source": "prometheus + node_exporter + application_metrics",
            "servers": {
                name: {
                    "hostname": m.hostname, "role": m.role,
                    "cpu_cores": m.cpu_cores, "cpu_usage_pct": m.cpu_usage,
                    "memory_total_gb": m.memory_total_gb, "memory_usage_pct": m.memory_usage,
                    "disk_total_gb": m.disk_total_gb, "disk_usage_pct": m.disk_usage,
                    "network_rx_mbps": m.network_rx_mbps, "network_tx_mbps": m.network_tx_mbps,
                    "load_avg": {"1m": m.load_avg_1m, "5m": m.load_avg_5m, "15m": m.load_avg_15m},
                    "open_files": m.open_files,
                    "tcp_connections": m.tcp_connections, "tcp_time_wait": m.tcp_time_wait,
                    "iowait_pct": m.iowait_pct,
                    "uptime_hours": m.uptime_hours,
                }
                for name, m in self.state.servers.items()
            },
            "services": {
                name: {
                    "type": s.service_type, "status": s.status,
                    "host": s.host, "port": s.port, "pid": s.pid, "replicas": s.replicas,
                    "latency": {"p50_ms": s.response_time_p50_ms, "p99_ms": s.response_time_p99_ms},
                    "error_rate": s.error_rate,
                    "request_count_1m": s.request_count_1m,
                    "restart_count": s.restart_count, "last_restart": s.last_restart,
                    "memory_rss_mb": s.memory_rss_mb,
                    "thread_count": s.thread_count,
                    "connection_pool": {"size": s.connection_pool_size, "active": s.connection_pool_active},
                    "heap_usage_pct": s.heap_usage_pct,
                    "gc_pause_ms": s.gc_pause_ms,
                    "circuit_breaker": s.circuit_breaker_state,
                }
                for name, s in self.state.services.items()
            },
            "dependencies": [
                {"from": d.upstream, "to": d.downstream, "protocol": d.protocol,
                 "timeout_ms": d.timeout_ms, "critical": d.critical}
                for d in self.state.dependencies
            ],
            "recent_logs": [
                {"timestamp": l.timestamp, "level": l.level, "source": l.source,
                 "message": l.message, "trace_id": l.trace_id}
                for l in self.state.logs[-30:]
            ],
            "active_incidents": [
                {"timestamp": e.timestamp, "type": e.event_type,
                 "agent": e.agent, "summary": e.summary}
                for e in self.state.events[-10:]
            ],
        }

    def get_service_logs(self, service_name: str, limit: int = 20) -> list:
        """Get logs for a specific service (for diagnostic deep-dive)."""
        return [
            {"timestamp": l.timestamp, "level": l.level, "source": l.source,
             "message": l.message, "trace_id": l.trace_id}
            for l in self.state.logs if l.source == service_name
        ][-limit:]

    def get_dependency_graph(self) -> list:
        """Return the service dependency graph."""
        return [
            {"upstream": d.upstream, "downstream": d.downstream,
             "protocol": d.protocol, "timeout_ms": d.timeout_ms, "critical": d.critical}
            for d in self.state.dependencies
        ]

    # )?)? Repair Actions ----)?)?)?)?)?)?)?

    def apply_fix(self, action: str, target: str, params: dict = None) -> dict:
        """Execute a repair action and return the result with post-fix snapshot."""
        now = datetime.now().strftime(TIMESTAMP_FMT)
        params = params or {}
        result = {
            "success": False,
            "action": action,
            "target": target,
            "message": "",
            "actions_taken": [],
            "side_effects": [],
            "rollback_available": False,
            "timestamp": now,
        }

        if action == "restart_service":
            result = self._fix_restart_service(target, now, result)
        elif action == "rollback_deploy":
            result = self._fix_rollback_deploy(target, now, result)
        elif action == "kill_process":
            result = self._fix_kill_process(target, now, result)
        elif action == "clear_cache":
            result = self._fix_clear_cache(now, result)
        elif action == "scale_up":
            result = self._fix_scale_up(target, now, result)
        elif action == "cleanup_disk":
            result = self._fix_cleanup_disk(target, now, result)
        elif action == "fix_config":
            result = self._fix_config(target, params, now, result)
        elif action == "add_index":
            result = self._fix_add_index(target, now, result)
        elif action == "failover_replica":
            result = self._fix_failover_replica(now, result)
        elif action == "drain_connections":
            result = self._fix_drain_connections(target, now, result)
        elif action == "circuit_breaker_reset":
            result = self._fix_circuit_breaker_reset(target, now, result)
        else:
            result["message"] = f"Unknown repair action: {action}"
            self.state.logs.append(LogEntry(now, "WARN", "repair-agent", f"Unknown action: {action}/{target}"))

        result["post_fix_snapshot"] = self.get_monitor_snapshot()
        return result

    def _fix_restart_service(self, target: str, now: str, result: dict) -> dict:
        if target not in self.state.services:
            result["message"] = f"Service not found: {target}"
            return result
        svc = self.state.services[target]
        old_pid = svc.pid
        svc.restart_count += 1
        svc.pid = random.randint(10000, 65000)
        svc.status = "running"
        svc.error_rate = 0.005
        svc.response_time_p50_ms = 30
        svc.response_time_p99_ms = 120
        svc.circuit_breaker_state = "closed"
        result["success"] = True
        result["message"] = f"Service {target} restarted (PID: {old_pid} -> {svc.pid})"
        result["actions_taken"] = [
            f"Sent SIGTERM to PID {old_pid}",
            f"Waited for graceful shutdown (timeout: 30s)",
            f"Started new instance: PID {svc.pid}",
            f"Health check passed on port {svc.port}",
        ]
        result["rollback_available"] = True
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            f"Service {target} restarted: PID {old_pid} -> {svc.pid}, health=OK"))
        return result

    def _fix_rollback_deploy(self, target: str, now: str, result: dict) -> dict:
        if target not in self.state.services:
            result["message"] = f"Service not found: {target}"
            return result
        svc = self.state.services[target]
        svc.status = "running"
        svc.error_rate = 0.005
        svc.response_time_p50_ms = 30
        svc.response_time_p99_ms = 120
        svc.heap_usage_pct = 45.0
        svc.gc_pause_ms = 15.0
        svc.restart_count = 0
        result["success"] = True
        result["message"] = f"Rolled back {target} to previous stable version"
        result["actions_taken"] = [
            f"Identified last stable image tag from registry",
            f"Deployed rollback image for {target}",
            f"Rolling restart: 2 pods updated",
            f"Health check passed, readiness probe OK",
        ]
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            f"Deployment rollback for {target} -- reverted to stable version"))
        return result

    def _fix_kill_process(self, target: str, now: str, result: dict) -> dict:
        result["success"] = True
        result["message"] = f"Process {target} killed (SIGKILL)"
        result["actions_taken"] = [f"Sent SIGKILL to PID {target}"]
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent", f"Process {target} killed"))
        return result

    def _fix_clear_cache(self, now: str, result: dict) -> dict:
        if "redis-cluster" in self.state.services:
            redis = self.state.services["redis-cluster"]
            redis.status = "running"
            redis.response_time_p50_ms = 0.8
            redis.response_time_p99_ms = 3.0
            redis.error_rate = 0.0
            redis.connection_pool_active = 500
            redis.restart_count = 0
        if "cache-queue-01" in self.state.servers:
            self.state.servers["cache-queue-01"].tcp_connections = 1500
            self.state.servers["cache-queue-01"].memory_usage = 35.0
        result["success"] = True
        result["message"] = "Redis cluster restarted and cache flushed"
        result["actions_taken"] = [
            "FLUSHALL on Redis cluster (cleared 12GB cached data)",
            "Reset maxclients to 10000",
            "Restarted Redis with fresh state",
            "Connection pool leak source: fixed unclosed connections in user-service",
        ]
        result["side_effects"] = [
            "Temporary cache miss storm (expected, ~30s warmup)",
            "DB read load increase expected for 2-5 minutes",
        ]
        # Reset dependent services
        for svc_name in ["user-service", "order-service", "inventory-service"]:
            if svc_name in self.state.services:
                svc = self.state.services[svc_name]
                svc.circuit_breaker_state = "half-open"
                svc.error_rate = 0.02
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            "Redis cluster cleared and restarted -- cache miss storm expected"))
        return result

    def _fix_scale_up(self, target: str, now: str, result: dict) -> dict:
        if target not in self.state.services:
            result["message"] = f"Service not found: {target}"
            return result
        svc = self.state.services[target]
        old_replicas = svc.replicas
        svc.replicas = max(svc.replicas, 3)
        svc.error_rate *= 0.3
        svc.response_time_p50_ms *= 0.5
        svc.response_time_p99_ms *= 0.6
        result["success"] = True
        result["message"] = f"Scaled {target} from {old_replicas} to {svc.replicas} replicas"
        result["actions_taken"] = [
            f"Triggered HPA scale-up: {old_replicas} -> {svc.replicas} replicas",
            f"Waiting for new pods to be Ready...",
            f"Updated load balancer upstream config",
            f"Traffic redistributed across {svc.replicas} instances",
        ]
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            f"Scaled {target}: {old_replicas} -> {svc.replicas} replicas"))
        return result

    def _fix_cleanup_disk(self, target: str, now: str, result: dict) -> dict:
        if "db-master-01" in self.state.servers:
            self.state.servers["db-master-01"].disk_usage = 62.0
        if "mysql-primary" in self.state.services:
            self.state.services["mysql-primary"].status = "running"
            self.state.services["mysql-primary"].error_rate = 0.0005
        if "mysql-replica" in self.state.services:
            self.state.services["mysql-replica"].status = "running"
        result["success"] = True
        result["message"] = "Disk space freed: 98.5% -> 62.0%"
        result["actions_taken"] = [
            "Purged binary logs older than 7 days: PURGE BINARY LOGS BEFORE '2024-XX-XX'",
            "Rotated slow query log: mv slow.log slow.log.1 && mysqladmin flush-logs",
            "Removed old slow logs (50GB freed)",
            "Updated logrotate config: binlog retention = 7 days",
            "Enabled automated binlog purge cron job",
        ]
        result["side_effects"] = [
            "Replicas may need to re-sync (monitoring replication lag)",
        ]
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            "Disk cleanup completed: 98.5% -> 62.0% -- binlog rotation configured"))
        return result

    def _fix_config(self, target: str, params: dict, now: str, result: dict) -> dict:
        result["success"] = True
        config_key = params.get("config_key", "PAYMENT_GATEWAY_SECRET")
        result["message"] = f"Config fixed for {target}: {config_key} injected"
        result["actions_taken"] = [
            f"Retrieved {config_key} from Vault/secret-manager",
            f"Updated ConfigMap for {target}",
            f"Triggered rolling restart with new config",
            f"Health check passed after config reload",
        ]
        if target in self.state.services:
            svc = self.state.services[target]
            svc.status = "running"
            svc.error_rate = 0.005
            svc.restart_count = 0
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            f"Config fixed for {target}: {config_key} injected from Vault"))
        return result

    def _fix_add_index(self, target: str, now: str, result: dict) -> dict:
        if "mysql-primary" in self.state.services:
            mysql = self.state.services["mysql-primary"]
            mysql.response_time_p50_ms = 8
            mysql.response_time_p99_ms = 45
            mysql.error_rate = 0.0005
            mysql.request_count_1m = 25000
        if "db-master-01" in self.state.servers:
            self.state.servers["db-master-01"].cpu_usage = 55.0
            self.state.servers["db-master-01"].iowait_pct = 8.0
            self.state.servers["db-master-01"].load_avg_1m = 5.0
        result["success"] = True
        result["message"] = f"Index added on {target}, query performance restored"
        result["actions_taken"] = [
            f"CREATE INDEX idx_orders_status_created ON orders(status, created_at)",
            f"Index build completed in 45s (online DDL, no table lock)",
            f"EXPLAIN plan verified: full-table scan -> index range scan",
            f"Slow query count dropped to 0",
        ]
        if "order-service" in self.state.services:
            self.state.services["order-service"].response_time_p50_ms = 80
            self.state.services["order-service"].response_time_p99_ms = 250
            self.state.services["order-service"].error_rate = 0.01
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            f"Index added on {target} -- query time restored to normal"))
        return result

    def _fix_failover_replica(self, now: str, result: dict) -> dict:
        if "mysql-replica" in self.state.services:
            replica = self.state.services["mysql-replica"]
            replica.status = "running"
            replica.response_time_p50_ms = 8
            replica.response_time_p99_ms = 45
        if "mysql-primary" in self.state.services:
            self.state.services["mysql-primary"].status = "running"
        result["success"] = True
        result["message"] = "Failover to replica completed"
        result["actions_taken"] = [
            "Promoted mysql-replica-01 to primary",
            "Updated DNS/VIP to point to new primary",
            "Redirected all write traffic to new primary",
            "Monitoring old primary for recovery",
        ]
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            "Database failover completed: replica promoted to primary"))
        return result

    def _fix_drain_connections(self, target: str, now: str, result: dict) -> dict:
        if target in self.state.services:
            svc = self.state.services[target]
            svc.connection_pool_active = min(svc.connection_pool_active, svc.connection_pool_size // 2)
        result["success"] = True
        result["message"] = f"Drained stale connections for {target}"
        result["actions_taken"] = [
            f"Identified and closed {random.randint(200, 500)} stale connections",
            f"Reset connection pool for {target}",
            f"Enabled connection health check (idle_timeout=60s)",
        ]
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            f"Connection pool drained for {target}"))
        return result

    def _fix_circuit_breaker_reset(self, target: str, now: str, result: dict) -> dict:
        if target in self.state.services:
            self.state.services[target].circuit_breaker_state = "half-open"
        result["success"] = True
        result["message"] = f"Circuit breaker reset to half-open for {target}"
        result["actions_taken"] = [
            f"Reset circuit breaker state: open -> half-open",
            f"Allowing probe requests through",
            f"Will auto-close after 3 successful probes",
        ]
        self.state.logs.append(LogEntry(now, "INFO", "repair-agent",
            f"Circuit breaker reset for {target}: open -> half-open"))
        return result

    # )?)? Health Check ----)?)?)?)?)?)?)?)?)?

    def health_check(self) -> dict:
        """Comprehensive post-repair health verification."""
        unhealthy_servers = []
        unhealthy_services = []
        slo_violations = []

        for name, s in self.state.servers.items():
            issues = []
            if s.cpu_usage > 90:
                issues.append(f"CPU={s.cpu_usage}%")
            if s.memory_usage > 92:
                issues.append(f"MEM={s.memory_usage}%")
            if s.disk_usage > 90:
                issues.append(f"DISK={s.disk_usage}%")
            if s.load_avg_1m > s.cpu_cores * 4:
                issues.append(f"LOAD_1m={s.load_avg_1m} (cores={s.cpu_cores})")
            if s.tcp_connections > 8000:
                issues.append(f"TCP={s.tcp_connections}")
            if s.iowait_pct > 30:
                issues.append(f"IOWAIT={s.iowait_pct}%")
            if issues:
                unhealthy_servers.append({"server": name, "role": s.role, "issues": issues})

        for name, svc in self.state.services.items():
            issues = []
            if svc.status == "down":
                issues.append("SERVICE DOWN")
            if svc.status == "degraded":
                issues.append("DEGRADED")
            if svc.error_rate > 0.10:
                issues.append(f"ErrorRate={svc.error_rate*100:.1f}%")
            if svc.response_time_p99_ms > 2000:
                issues.append(f"p99={svc.response_time_p99_ms}ms")
            if svc.restart_count > 2:
                issues.append(f"Restarts={svc.restart_count}")
            if svc.circuit_breaker_state == "open":
                issues.append("CircuitBreaker=OPEN")
            if svc.heap_usage_pct > 90:
                issues.append(f"Heap={svc.heap_usage_pct}%")
            if svc.gc_pause_ms > 1000:
                issues.append(f"GC_Pause={svc.gc_pause_ms}ms")
            if issues:
                unhealthy_services.append({"service": name, "type": svc.service_type, "issues": issues})

        # SLO check
        for name, svc in self.state.services.items():
            if svc.error_rate > 0.001:  # 99.9% SLO
                slo_violations.append({
                    "service": name,
                    "slo_target": "99.9%",
                    "current_availability": f"{(1 - svc.error_rate) * 100:.2f}%",
                })

        overall = "healthy"
        p0_down = any(s.status == "down" for s in self.state.services.values())
        if p0_down or len(unhealthy_services) >= 3:
            overall = "critical"
        elif unhealthy_services:
            overall = "degraded"
        elif unhealthy_servers:
            overall = "warning"

        return {
            "overall": overall,
            "timestamp": datetime.now().strftime(TIMESTAMP_FMT),
            "unhealthy_servers": unhealthy_servers,
            "unhealthy_services": unhealthy_services,
            "slo_violations": slo_violations,
            "total_servers": len(self.state.servers),
            "total_services": len(self.state.services),
            "healthy_servers": len(self.state.servers) - len(unhealthy_servers),
            "healthy_services": len(self.state.services) - len(unhealthy_services),
        }