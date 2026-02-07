
import inspect
from src.utils.opgg_client import OPGGClient, opgg_client

def debug():
    print(f"Type of opgg_client: {type(opgg_client)}")
    print(f"MRO of OPGGClient: {inspect.getmro(OPGGClient)}")
    
    print("\nInspecting _prepare_opgg_params...")
    method = opgg_client._prepare_opgg_params
    print(f"Type of method: {type(method)}")
    print(f"Signature of method: {inspect.signature(method)}")
    
    try:
        print("\nCalling method manually...")
        res = method("https://example.com")
        print(f"Manual call result: {res}")
    except Exception as e:
        print(f"Manual call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug()
