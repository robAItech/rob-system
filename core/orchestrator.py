from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.gstack_bridge import GSTACKArchitectBridge
from core.hermes_bridge import HermesBuilderBridge
from core.loopx_bridge import LoopXEngineBridge

class RobAIOrchestrator:
    @staticmethod
    def run(project: str, directive: str) -> bool:
        print(f"🚀 [ROB AI STUDIO] Inicializacija zahteve za modul: '{project}'")
        print(f"📜 Direktiva: '{directive}'")

        # 1. GBRAIN: Pridobivanje konteksta in prepovedanih vzorcev
        gbrain = GBrainBridge()
        blacklists = gbrain.get_blacklists(project)

        # 2. GRAPHIFY: Posodobitev in analiza AST grafa
        graphify = GraphifyBridge()
        graphify.build_code_graph()

        # 3. GSTACK: Razčlenitev arhitekture v specifikacijo
        gstack = GSTACKArchitectBridge(blacklists)
        manifest = gstack.generate_manifest(project, directive)
        print(f"🏗️ GSTACK Specifikacija ustvarjena ({len(manifest['files'])} datoteke)")

        # 4. HERMES: Izdelava datotek in ogrodja
        hermes = HermesBuilderBridge(project)
        hermes.write_initial_stubs_if_missing()

        # 5. LOOPX: Izvajanje verifikacijske in samoozdravitvene zanke
        loopx = LoopXEngineBridge(project)
        success = loopx.execute_and_heal(directive)

        if success:
            print(f"✅ Modul '{project}' uspešno potrjen (100% VERIFIED GREEN)!")
        else:
            print(f"❌ Napaka pri verifikaciji modula '{project}'. Traceback zablokiran v GBRAIN.")

        return success