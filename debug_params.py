
import inspect
from opgg.v2.opgg import OPGG
from opgg.v2.utils import Utils

def debug():
    print("Inspecting OPGG class...")
    for name, obj in inspect.getmembers(OPGG):
        if "_get_params" in name:
            print(f"Found OPGG member: {name}, signature: {inspect.signature(obj) if callable(obj) else 'not callable'}")
            
    print("\nInspecting Utils class...")
    for name, obj in inspect.getmembers(Utils):
        if "_get_params" in name:
            print(f"Found Utils member: {name}, signature: {inspect.signature(obj) if callable(obj) else 'not callable'}")

    print("\nCheck if our OPGGClient has the method...")
    from src.utils.opgg_client import OPGGClient
    client = OPGGClient()
    for name, obj in inspect.getmembers(client):
        if "_get_params" in name:
            print(f"Found OPGGClient member: {name}, signature: {inspect.signature(obj) if callable(obj) else 'not callable'}")

if __name__ == "__main__":
    debug()
