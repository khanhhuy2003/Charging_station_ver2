import json


def json_build_charger_response(ds): #for demo ver 1, charger respone
    return json.dumps({
        "charger_name": ds["charger_name"],
        "charger_MAC": ds["charger_MAC"],
        "request_id": ds.get("request_id"),
        "battery": {str(i+1): ds["battery"][i] for i in range(5)},
        "status": ds["status"].name,
        "charging": {
            "progress": ds["progress"].name,
            "estimate_time": ds["estimate_time"],
            "error": {
                "id": ds["error_id"],
                "detail": ds["error_detail"]
            }
        }
    })
#def json_build_v2(ds):

def parse_json(payload):
    try:
        return json.loads(payload)
    except Exception:
        return None