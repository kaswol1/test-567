from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# --- KONFIGURACJA ---
PIPEDRIVE_API_TOKEN = os.getenv("PIPEDRIVE_API_TOKEN")  # Ustaw jako zmienna środowiskowa
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")   # np. twojafirma.atlassian.net

JIRA_PROJECT_KEY = "RQIMP"
JIRA_ISSUE_TYPE = "Task"

# Mapowanie pól
JIRA_FIELDS = {
    "typ_prezentacji": "customfield_1008",
    "date_1": "customfield_10090",
    "date_2": "customfield_10089",
    "date_3": "customfield_10091",
    "partner": "customfield_10092",
}

# --- HELPERY ---

def get_deal(deal_id):
    url = f"https://api.pipedrive.com/v1/deals/{deal_id}?api_token={PIPEDRIVE_API_TOKEN}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json().get("data")

def get_org(org_id):
    url = f"https://api.pipedrive.com/v1/organizations/{org_id}?api_token={PIPEDRIVE_API_TOKEN}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json().get("data")

def create_jira_issue(fields):
    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)

    issue_data = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": f"Nowy deal: {fields['deal_title']}",
            "description": f"Organizacja: {fields['org_name']}",
            "issuetype": {"name": JIRA_ISSUE_TYPE},
            JIRA_FIELDS["typ_prezentacji"]: {"id": fields["typ_prezentacji_id"]},
            JIRA_FIELDS["date_1"]: fields.get("date1"),
            JIRA_FIELDS["date_2"]: fields.get("date2"),
            JIRA_FIELDS["date_3"]: fields.get("date3"),
            JIRA_FIELDS["partner"]: fields.get("partner")
        }
    }

    headers = {"Content-Type": "application/json"}
    res = requests.post(url, auth=auth, json=issue_data, headers=headers)
    res.raise_for_status()
    return res.json()

# --- ENDPOINT ---
@app.route("/webhook", methods=["POST"])
def pipedrive_webhook():
    data = request.json
    deal_id = data.get("current", {}).get("id")
    org_id = data.get("current", {}).get("org_id")

    if not deal_id or not org_id:
        return jsonify({"error": "Brak deal_id lub org_id"}), 400

    try:
        deal = get_deal(deal_id)
        org = get_org(org_id)

        fields = {
            "deal_title": deal.get("title"),
            "typ_prezentacji_id": deal.get("5bc985e61592b58e001c657305423499b6a23ce4"),
            "date1": deal.get("77554ed03246265be68e75bc152243b19d492d9f"),
            "date2": deal.get("348bc2d5699beb5a76ae34f9318055a0bbbef3a8"),
            "date3": deal.get("db137c6e874446aaa7e42d1638538f5138786633"),
            "org_name": org.get("name"),
            "partner": org.get("fea50f9d3ff5801b5fa9c451a8110445442db46d")
        }

        jira_response = create_jira_issue(fields)
        return jsonify(jira_response), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- RUN ---
if __name__ == "__main__":
    app.run(debug=True, port=5000)
