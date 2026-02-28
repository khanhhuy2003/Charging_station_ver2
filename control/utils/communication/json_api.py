import json
from control.utils.var_shared_utils import RobotSendData, ChargerSendData

def json_build_charger_response(ds, status : ChargerSendData): 
    return json.dumps({
        "charger_name": ds["charger_name"],
        "charger_MAC": ds["charger_MAC"],
        "request_id": ds.get("request_id"),
        "battery": {str(i+1): ds["battery"][i] for i in range(5)},
        "status": ds["status"].name,
        "charging": {
            "progress": status.progress,
            "estimate_time": ds["estimate_time"],
            "error": {
                "id": ds["error_id"],
                "detail": ds["error_detail"]
            }
        }
    })


def parse_json(payload):
    try:
        return json.loads(payload)
    except Exception:
        return None