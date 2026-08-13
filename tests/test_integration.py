from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.gstack_bridge import GSTACKArchitectBridge

def test_gbrain_memory_roundtrip():
    gbrain = GBrainBridge()
    task_id = gbrain.record_task("test_proj", "test prompt", "VERIFIED GREEN", "", "code")
    assert task_id > 0

def test_graphify_ast_indexing():
    graphify = GraphifyBridge()
    graph = graphify.build_code_graph()
    assert "nodes" in graph

def test_gstack_manifest_generation():
    gstack = GSTACKArchitectBridge(blacklists=[])
    manifest = gstack.generate_manifest("demo_service", "Build demo endpoint")
    assert manifest["project_name"] == "demo_service"
