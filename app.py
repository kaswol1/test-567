from flask import Flask, request, jsonify
import requests
import os
import logging
import io # Do obsługi plików w pamięci

app = Flask(__name__)

# --- KONFIGURACJA LOGOWANIA ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- KONFIGURACJA API ---
# Zmienne środowiskowe pobierane z Render.com
PIPEDRIVE_API_TOKEN = os.getenv("PIPEDRIVE_API_TOKEN")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN")

# Sprawdzenie, czy zmienne środowiskowe są ustawione
if not PIPEDRIVE_API_TOKEN:
    logging.error("BŁĄD KONFIGURACJI: PIPEDRIVE_API_TOKEN nie jest ustawiony!")
if not JIRA_API_TOKEN:
    logging.error("BŁĄD KONFIGURACJI: JIRA_API_TOKEN nie jest ustawiony!")
if not JIRA_EMAIL:
    logging.error("BŁĄD KONFIGURACJI: JIRA_EMAIL nie jest ustawiony!")
if not JIRA_DOMAIN:
    logging.error("BŁĄD KONFIGURACJI: JIRA_DOMAIN nie jest ustawiony!")


JIRA_PROJECT_KEY = "RQIMP" # Klucz projektu Jira
JIRA_ISSUE_TYPE = "Task"    # Typ zadania Jira

# Mapowanie pól Jira (zaktualizowane o ID Klienta)
JIRA_FIELDS = {
    "typ_prezentacji": "customfield_1008",
    "klient": "customfield_10086", # Nowe pole: Klient
    "date_1": "customfield_10090",
    "date_2": "customfield_10089",
    "date_3": "customfield_10091",
    "partner": "customfield_10092",
}

# Mapowanie opcji dla pola Typ Prezentacji Technicznej (Pipedrive ID -> Jira ID)
# Pipedrive zwraca ID jako string, Jira oczekuje ID jako string
TYP_PREZENTACJI_MAPPING = {
    "32": {"id": "32"}, # Pipedrive ID "32" -> Jira Option ID "32" ("Prezentacja wprowadzająca")
    "33": {"id": "33"}, # Pipedrive ID "33" -> Jira Option ID "33" ("Prezentacja techniczna")
    "68": {"id": "68"}, # Pipedrive ID "68" -> Jira Option ID "68" ("PoC")
    "69": {"id": "69"}, # Pipedrive ID "69" -> Jira Option ID "69" ("Demo")
    "70": {"id": "70"}, # Pipedrive ID "70" -> Jira Option ID "70" ("Rozmowa referencyjna")
}

# --- HELPERY (Funkcje pomocnicze do komunikacji z API) ---

def get_deal(deal_id):
    """Pobiera szczegóły deala z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony. Nie można pobrać deala.")
        return None
    url = f"https://api.pipedrive.com/v1/deals/{deal_id}?api_token={PIPEDRIVE_API_TOKEN}"
    try:
        res = requests.get(url)
        res.raise_for_status() # Wyrzuci błąd dla statusów 4xx/5xx
        return res.json().get("data")
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania deala {deal_id} z Pipedrive: {e}")
        return None

def get_org(org_id):
    """Pobiera szczegóły organizacji z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony. Nie można pobrać organizacji.")
        return None
    url = f"https://api.pipedrive.com/v1/organizations/{org_id}?api_token={PIPEDRIVE_API_TOKEN}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json().get("data")
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania organizacji {org_id} z Pipedrive: {e}")
        return None

def get_deal_attachments(deal_id):
    """Pobiera listę załączników (plików) dla danego deala z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony. Nie można pobrać załączników.")
        return []
    # Endpoint files?deal_id={deal_id} zwróci tylko pliki przypisane bezpośrednio do deala
    # Można też użyć files?entity_type=deal&entity_id={deal_id}
    url = f"https://api.pipedrive.com/v1/files?deal_id={deal_id}&api_token={PIPEDRIVE_API_TOKEN}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        # Zwracamy listę obiektów plików
        return res.json().get("data", [])
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania załączników dla deala {deal_id} z Pipedrive: {e}")
        return []

def download_file_from_pipedrive(file_id):
    """Pobiera zawartość pliku z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony. Nie można pobrać pliku.")
        return None
    url = f"https://api.pipedrive.com/v1/files/{file_id}/download?api_token={PIPEDRIVE_API_TOKEN}"
    try:
        res = requests.get(url, stream=True) # stream=True dla dużych plików
        res.raise_for_status()
        return res.content # Zwracamy surową zawartość pliku
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania pliku {file_id} z Pipedrive: {e}")
        return None

def create_jira_issue(fields):
    """Tworzy zadanie w Jira z podanymi polami."""
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN]):
        logging.error("Brak pełnych danych uwierzytelniających Jira. Nie można utworzyć zadania.")
        return {"error": "Jira credentials missing"}

    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Content-Type": "application/json"}

    # Przygotowanie pól dla Jira
    jira_issue_fields = {
        "project": {"key": JIRA_PROJECT_KEY},
        "summary": fields["deal_title"],
        "description": f"Organizacja: {fields['org_name'] or 'Brak nazwy organizacji'}\nDeal ID: {fields['deal_id']}",
        "issuetype": {"name": JIRA_ISSUE_TYPE},
    }

    # Dodawanie pól niestandardowych tylko jeśli mają wartości
    # Typ Prezentacji Technicznej (customfield_1008)
    if fields.get("typ_prezentacji_jira_format"):
        jira_issue_fields[JIRA_FIELDS["typ_prezentacji"]] = fields["typ_prezentacji_jira_format"]
    else:
        logging.warning("Pole 'Typ Prezentacji Technicznej' jest puste lub niepoprawne.")

    # Pole Klient (customfield_10086) - tekstowe
    if fields.get("klient"):
        jira_issue_fields[JIRA_FIELDS["klient"]] = fields["klient"]
    else:
        logging.info("Pole 'Klient' jest puste.")

    # Pola dat (customfield_10090, customfield_10089, customfield_10091) - format YYYY-MM-DD
    if fields.get("date1"):
        jira_issue_fields[JIRA_FIELDS["date_1"]] = fields["date1"]
    if fields.get("date2"):
        jira_issue_fields[JIRA_FIELDS["date_2"]] = fields["date2"]
    if fields.get("date3"):
        jira_issue_fields[JIRA_FIELDS["date_3"]] = fields["date3"]

    # Pole Partner (customfield_10092) - tekstowe
    if fields.get("partner"):
        jira_issue_fields[JIRA_FIELDS["partner"]] = fields["partner"]
    else:
        logging.info("Pole 'Partner' jest puste.")


    issue_data = {"fields": jira_issue_fields}
    logging.info(f"Wysyłanie danych do Jira: {issue_data}") # Logowanie danych wysyłanych do Jira

    res = None # Inicjalizacja res na None
    try:
        res = requests.post(url, auth=auth, json=issue_data, headers=headers)
        res.raise_for_status()
        logging.info(f"Zadanie Jira utworzone pomyślnie. Klucz: {res.json().get('key')}, ID: {res.json().get('id')}")
        return res.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas tworzenia zadania Jira: {e}")
        if res is not None:
            logging.error(f"Odpowiedź Jira: {res.text}")
        raise # Ponownie zgłoś błąd, aby został złapany przez główny blok except

def upload_attachment_to_jira(issue_id_or_key, filename, file_content):
    """Przesyła pojedynczy załącznik do zadania Jira."""
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN]):
        logging.error("Brak pełnych danych uwierzytelniających Jira. Nie można przesłać załącznika.")
        return {"error": "Jira credentials missing"}

    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_id_or_key}/attachments"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {
        "X-Atlassian-Token": "no-check" # Wymagane przez Jira dla załączników
    }

    files = {
        'file': (filename, io.BytesIO(file_content)) # Plik binarny z nazwą
    }

    try:
        res = requests.post(url, auth=auth, files=files, headers=headers)
        res.raise_for_status()
        logging.info(f"Załącznik '{filename}' dodany do zadania Jira {issue_id_or_key}.")
        return res.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas przesyłania załącznika '{filename}' do Jira {issue_id_or_key}: {e}")
        if res is not None:
            logging.error(f"Odpowiedź Jira: {res.text}")
        return {"error": f"Failed to upload attachment {filename}: {e}"}

# --- ENDPOINT (Główna logika aplikacji) ---
@app.route("/webhook", methods=["POST"])
def pipedrive_webhook():
    logging.info("Otrzymano żądanie webhooka Pipedrive.")
    try:
        data = request.json
        logging.info(f"Odebrano dane JSON: {data}")

        # Oczekujemy, że webhook Pipedrive wyśle tylko deal_id i org_id
        deal_id = data.get("deal_id")
        org_id = data.get("org_id")

        if not deal_id or not org_id:
            logging.warning(f"Brak deal_id lub org_id w otrzymanym JSON: {data}")
            return jsonify({"error": "Brak deal_id lub org_id w body JSON. Oczekiwano {'deal_id': ..., 'org_id': ...}"}), 400

        logging.info(f"Pobieranie danych dla deal_id: {deal_id}, org_id: {org_id}")

        deal = get_deal(deal_id)
        if not deal:
            logging.error(f"Nie udało się pobrać deala o ID {deal_id}.")
            return jsonify({"error": f"Nie udało się pobrać deala {deal_id}"}), 500

        org = get_org(org_id)
        if not org:
            logging.error(f"Nie udało się pobrać organizacji o ID {org_id}.")
            return jsonify({"error": f"Nie udało się pobrać organizacji {org_id}"}), 500

        # --- PRZETWARZANIE DANYCH ---
        # Pobieranie wartości pól niestandardowych z deala Pipedrive
        typ_prezentacji_pipedrive_id = deal.get("5bc985e61592b58e001c657305423499b6a23ce4")
        date1 = deal.get("77554ed03246265be68e75bc152243b19d492d9f")
        date2 = deal.get("348bc2d5699beb5a76ae34f9318055a0bbbef3a8")
        date3 = deal.get("db137c6e874446aaa7e42d1638538f5138786633")

        # Pobieranie wartości pola 'partner' z organizacji Pipedrive
        partner = org.get("fea50f9d3ff5801b5fa9c451a8110445442db46d")

        logging.info(f"Pobrane wartości z Pipedrive: "
                     f"Typ Prezentacji: {typ_prezentacji_pipedrive_id}, "
                     f"Data 1: {date1}, Data 2: {date2}, Data 3: {date3}, "
                     f"Partner: {partner}")

        # Mapowanie 'Typ Prezentacji Technicznej' z Pipedrive ID na Jira Option ID
        typ_prezentacji_jira_format = []
        if typ_prezentacji_pipedrive_id:
            # Pipedrive dla pola typu 'set' zwraca listę ID, nawet jeśli jest tylko jeden wybrany
            # Lub czasem pojedyncze ID jako string, jeśli tak było w poprzednim kodzie.
            # Zabezpieczamy się na oba przypadki:
            if isinstance(typ_prezentacji_pipedrive_id, list):
                for pid in typ_prezentacji_pipedrive_id:
                    jira_option = TYP_PREZENTACJI_MAPPING.get(str(pid))
                    if jira_option:
                        typ_prezentacji_jira_format.append(jira_option)
                    else:
                        logging.warning(f"Nie znaleziono mapowania Jira dla Pipedrive ID: {pid}")
            else: # pojedyncze ID (jeśli Pipedrive zwróciło tylko jeden wybór)
                jira_option = TYP_PREZENTACJI_MAPPING.get(str(typ_prezentacji_pipedrive_id))
                if jira_option:
                    typ_prezentacji_jira_format.append(jira_option)
                else:
                    logging.warning(f"Nie znaleziono mapowania Jira dla Pipedrive ID: {typ_prezentacji_pipedrive_id}")
        else:
            logging.info("Pole 'Typ Prezentacji Technicznej' z Pipedrive jest puste.")


        # Przygotowanie słownika pól do przekazania do funkcji create_jira_issue
        fields_for_jira = {
            "deal_id": deal_id,
            "deal_title": deal.get("title", "Brak tytułu deala"),
            "org_name": org.get("name", "Brak nazwy organizacji"),
            "klient": org.get("name", ""), # Pole Klient w Jira
            "typ_prezentacji_jira_format": typ_prezentacji_jira_format,
            "date1": date1, # Format YYYY-MM-DD
            "date2": date2, # Format YYYY-MM-DD
            "date3": date3, # Format YYYY-MM-DD
            "partner": partner # Puste jeśli None
        }

        jira_response = create_jira_issue(fields_for_jira)
        jira_issue_key = jira_response.get('key')
        jira_issue_id = jira_response.get('id')

        # --- PRZESYŁANIE ZAŁĄCZNIKÓW DO JIRA ---
        if jira_issue_key:
            logging.info(f"Pobieranie załączników dla deala {deal_id}...")
            attachments = get_deal_attachments(deal_id)
            if attachments:
                logging.info(f"Znaleziono {len(attachments)} załączników dla deala {deal_id}.")
                for attachment in attachments:
                    file_id = attachment.get('id')
                    file_name = attachment.get('file_name')
                    if file_id and file_name:
                        logging.info(f"Pobieranie pliku '{file_name}' (ID: {file_id}) z Pipedrive...")
                        file_content = download_file_from_pipedrive(file_id)
                        if file_content:
                            logging.info(f"Przesyłanie pliku '{file_name}' do Jira...")
                            upload_attachment_to_jira(jira_issue_key, file_name, file_content)
                        else:
                            logging.warning(f"Nie udało się pobrać zawartości pliku '{file_name}' (ID: {file_id}).")
                    else:
                        logging.warning(f"Brak ID pliku lub nazwy dla załącznika: {attachment}")
            else:
                logging.info(f"Brak załączników dla deala {deal_id}.")
        else:
            logging.error("Nie udało się uzyskać klucza zadania Jira. Nie można przesłać załączników.")


        logging.info("Zakończono przetwarzanie webhooka Pipedrive.")
        return jsonify(jira_response), 201

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 500
        error_message = e.response.text if e.response is not None else str(e)
        logging.error(f"Błąd HTTP: Status {status_code}, Wiadomość: {error_message}", exc_info=True)
        return jsonify({"error": f"Błąd HTTP: {status_code} - {error_message}"}), status_code
    except Exception as e:
        logging.error(f"Wystąpił nieoczekiwany błąd: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --- RUN ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
