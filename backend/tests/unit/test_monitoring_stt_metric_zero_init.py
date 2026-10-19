"""Startup exposition contract for alert metrics in the two Python registries.

Scope: every Prometheus expr in alerts/*.json, intersected with metrics defined
in utils/metrics.py and llm_gateway/gateway/metrics.py (regardless of job selector).
Exporter, GPU and other service registries are outside this contract. This checks
family availability, not completeness of every possible label selector.
"""

import ast
import importlib
from pathlib import Path

import pytest
from prometheus_client import Counter, Gauge, Histogram

BACKEND = Path(__file__).resolve().parents[2]

def _module_calls(path):
    """Calls outside function/class bodies: defining an initializer isn't enough."""
    calls = set()

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            pass

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            self.generic_visit(node)

    Visitor().visit(ast.parse(path.read_text(encoding='utf-8')))
    return calls


def _startup_inventory():
    # Only pure instrumentation modules are imported; no servers, pollers or
    # provider clients are started. Import executes their real zero-init paths.
    metrics = importlib.import_module('utils.metrics')
    gateway_metrics = importlib.import_module('llm_gateway.gateway.metrics')
    for name in ('fallback', 'transcription'):
        importlib.import_module(f'utils.observability.{name}')
    importlib.import_module('utils.stt.stream_close')
    connect = importlib.import_module('utils.stt.connect_metrics')
    # streaming.py is a heavy provider entrypoint. Prove its startup call is
    # wired, then invoke the same lightweight initializer without importing SDKs.
    assert 'initialize_stt_provider_connect_children' in _module_calls(BACKEND / 'utils/stt/streaming.py')
    connect.initialize_stt_provider_connect_children()
    inventory = {}
    for module in (metrics, gateway_metrics):
        for metric in vars(module).values():
            if not isinstance(metric, (Counter, Gauge, Histogram)):
                continue
            names = {metric._name}
            if isinstance(metric, Counter):
                names = {metric._name + '_total'}
            elif isinstance(metric, Histogram):
                names |= {metric._name + suffix for suffix in ('_bucket', '_count', '_sum')}
            for name in names:
                inventory[name] = metric
    return inventory


@pytest.fixture(scope='module')
def startup_inventory():
    return _startup_inventory()


def test_close_initializer_is_wired_for_streaming_and_direct_vendor_users():
    initializer = 'initialize_stt_stream_close_children'
    assert initializer in _module_calls(BACKEND / 'utils/stt/streaming.py')
    assert initializer in _module_calls(BACKEND / 'utils/stt/stream_close.py')
