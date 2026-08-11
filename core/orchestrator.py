from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.gstack_bridge import GSTACKArchitectBridge
from core.hermes_bridge import HermesBuilderBridge
from core.loopx_bridge import LoopXEngineBridge

class RobAIOrchestrator:
    @staticmethod
    def run(project: str, directive: str) -> bool:
        gbrain = GBrainBridge()
        blacklists = gbrain.get_blacklists(project)

        graphify = GraphifyBridge()
        graphify.build_code_graph()

        gstack = GSTACKArchitectBridge(blacklists)
        manifest = gstack.generate_manifest(project, directive)

        hermes = HermesBuilderBridge(project)
        hermes.scaffold()

        loopx = LoopXEngineBridge(project)
        return loopx.execute_and_heal(directive)
