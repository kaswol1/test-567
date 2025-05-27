from flask import Flask, request, jsonify
import requests
import os
import logging
import io # Importujemy moduł do obsługi strumieni bajtów w pamięci

# --- KONFIGURACJA APLIKACJI FLASK ---
app = Flask(__name__)

# --- KONFIGURACJA LOGOWANIA ---
# Ustawienie poziomu logowania na INFO, aby widzieć więcej szczegółów w logach Render.com
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- KONFIGURACJA DANYCH DOSTĘPOWYCH API (ZMIENNE ŚRODOWISKOWE Z RENDER.COM) ---
PIPEDRIVE_API_TOKEN = os.getenv("PIPEDRIVE_API_TOKEN")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN") # Np. twojafirma.atlassian.net

# Sprawdzenie, czy wszystkie kluczowe zmienne środowiskowe są ustawione
# Aplikacja będzie logować błędy, jeśli ich brakuje, ale nie przerwie działania,
# dopóki nie spróbuje użyć brakującego tokena.
if not PIPEDRIVE_API_TOKEN:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa PIPEDRIVE_API_TOKEN nie jest ustawiona.")
if not JIRA_API_TOKEN:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa JIRA_API_TOKEN nie jest ustawiona.")
if not JIRA_EMAIL:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa JIRA_EMAIL nie jest ustawiona.")
if not JIRA_DOMAIN:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa JIRA_DOMAIN nie jest ustawiona. Np. 'yourcompany.atlassian.net'")

# --- KONFIGURACJA PROJEKTU JIRA ---
JIRA_PROJECT_KEY = "RQIMP" # Klucz projektu Jira, np. "RQIMP"
JIRA_ISSUE_TYPE = "Zadanie"    # Typ zadania Jira, np. "Task", "Story", "Bug"

# --- MAPOWANIE PÓL NIESTANDARDOWYCH ---

# Hashe pól niestandardowych Pipedrive (z Twojej instancji Pipedrive)
PIPEDRIVE_CUSTOM_FIELDS_HASHES = {
    "typ_prezentacji_tech": "5bc985e61592b58e001c657305423499b6a23ce4",
    "data_1": "77554ed03246265be68e75bc152243b19d492d9f",
    "data_2": "348bc2d5699beb5a76ae34f9318055a0bbbef3a8",
    "data_3": "db137c6e874446aaa7e42d1638538f5138786633",
    "partner_org_field": "fea50f9d3ff5801b5fa9c451a8110445442db46d" # Pole 'Partner' z obiektu organizacji
}

# ID pól niestandardowych Jira (z Twojej instancji Jira)
JIRA_CUSTOM_FIELDS_IDS = {
    "typ_prezentacji_tech": "customfield_1008",
    "klient": "customfield_10086",
    "data_1": "customfield_10090",
    "data_2": "customfield_10089",
    "data_3": "customfield_10091",
    "partner": "customfield_10092"
}

# Mapowanie opcji dla pola 'Typ Prezentacji Technicznej'
# Klucz: ID opcji z Pipedrive (jako string)
# Wartość: Obiekt oczekiwany przez Jira dla pola typu 'Single/Multi Choice Select'
TYP_PREZENTACJI_MAPPING = {
    "32": {"id": "32"}, # Prezentacja wprowadzająca
    "33": {"id": "33"}, # Prezentacja techniczna
    "68": {"id": "68"}, # PoC
    "69": {"id": "69"}, # Demo
    "70": {"id": "70"}, # Rozmowa referencyjna
}

# --- FUNKCJE POMOCNICZE (KOMUNIKACJA Z API) ---

def get_deal_from_pipedrive(deal_id):
    """Pobiera szczegóły deala z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony.")
        return None
    url = f"https://api.pipedrive.com/v1/deals/{deal_id}?api_token={PIPEDRIVE_API_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status() # Wyrzuci wyjątek dla statusów 4xx/5xx
        return response.json().get("data")
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania deala {deal_id} z Pipedrive: {e}")
        if response is not None:
            logging.error(f"Odpowiedź Pipedrive: {response.text}")
        return None

def get_organization_from_pipedrive(org_id):
    """Pobiera szczegóły organizacji z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony.")
        return None
    url = f"https://api.pipedrive.com/v1/organizations/{org_id}?api_token={PIPEDRIVE_API_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get("data")
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania organizacji {org_id} z Pipedrive: {e}")
        if response is not None:
            logging.error(f"Odpowiedź Pipedrive: {response.text}")
        return None

def get_attachments_from_pipedrive(deal_id):
    """Pobiera listę załączników (plików) dla danego deala z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony.")
        return []
    url = f"https://api.pipedrive.com/v1/files?deal_id={deal_id}&api_token={PIPEDRIVE_API_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get("data", []) # Zwraca listę obiektów plików
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania załączników dla deala {deal_id} z Pipedrive: {e}")
        if response is not None:
            logging.error(f"Odpowiedź Pipedrive: {response.text}")
        return []

def download_file_content_from_pipedrive(file_id):
    """Pobiera binarną zawartość pliku z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony.")
        return None
    url = f"https://api.pipedrive.com/v1/files/{file_id}/download?api_token={PIPEDRIVE_API_TOKEN}"
    try:
        response = requests.get(url, stream=True) # Używamy stream=True dla wydajności przy dużych plikach
        response.raise_for_status()
        return response.content # Zwraca surową zawartość pliku (bajty)
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania zawartości pliku {file_id} z Pipedrive: {e}")
        if response is not None:
            logging.error(f"Odpowiedź Pipedrive: {response.text}")
        return None

def create_jira_issue(fields_to_create):
    """Tworzy zadanie w Jira z podanymi polami."""
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN]):
        logging.error("Brak pełnych danych uwierzytelniających Jira (DOMAIN, EMAIL, API_TOKEN). Nie można utworzyć zadania.")
        raise ValueError("Missing Jira credentials")

    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Content-Type": "application/json"}

    # Struktura danych dla Jira API
    jira_issue_payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": fields_to_create.get("deal_title", "Nowy deal (brak tytułu)"),
            "description": f"Organizacja: {fields_to_create.get('org_name', 'Brak nazwy organizacji')}\n"
                           f"Deal ID: {fields_to_create.get('deal_id', 'Brak ID deala')}",
            "issuetype": {"name": JIRA_ISSUE_TYPE},
        }
    }

    # Dodawanie pól niestandardowych tylko, jeśli mają wartości
    # customfield_1008: Typ Prezentacji Technicznej (multi-select w Jira, oczekuje listy obiektów {"id": "..."})
    if fields_to_create.get("typ_prezentacji_tech_jira_format"):
        jira_issue_payload["fields"][JIRA_CUSTOM_FIELDS_IDS["typ_prezentacji_tech"]] = \
            fields_to_create["typ_prezentacji_tech_jira_format"]
    else:
        logging.info("Pole 'Typ Prezentacji Technicznej' jest puste lub niepoprawne w Pipedrive.")

    # customfield_10086: Klient (tekstowe)
    if fields_to_create.get("klient"):
        jira_issue_payload["fields"][JIRA_CUSTOM_FIELDS_IDS["klient"]] = \
            fields_to_create["klient"]
    else:
        logging.info("Pole 'Klient' jest puste.")

    # Pola dat (tekstowe, format YYYY-MM-DD)
    if fields_to_create.get("data_1"):
        jira_issue_payload["fields"][JIRA_CUSTOM_FIELDS_IDS["data_1"]] = fields_to_create["data_1"]
    if fields_to_create.get("data_2"):
        jira_issue_payload["fields"][JIRA_CUSTOM_FIELDS_IDS["data_2"]] = fields_to_create["data_2"]
    if fields_to_create.get("data_3"):
        jira_issue_payload["fields"][JIRA_CUSTOM_FIELDS_IDS["data_3"]] = fields_to_create["data_3"]

    # customfield_10092: Partner (tekstowe)
    if fields_to_create.get("partner"):
        jira_issue_payload["fields"][JIRA_CUSTOM_FIELDS_IDS["partner"]] = \
            fields_to_create["partner"]
    else:
        logging.info("Pole 'Partner' jest puste.")

    logging.info(f"Wysyłanie danych do Jira: {jira_issue_payload}")

    response = None
    try:
        response = requests.post(url, auth=auth, json=jira_issue_payload, headers=headers)
        response.raise_for_status() # Sprawdza, czy odpowiedź jest 2xx
        jira_response_data = response.json()
        logging.info(f"Zadanie Jira utworzone pomyślnie. Klucz: {jira_response_data.get('key')}, ID: {jira_response_data.get('id')}")
        return jira_response_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas tworzenia zadania Jira: {e}")
        if response is not None:
            logging.error(f"Odpowiedź Jira (BŁĄD): {response.text}")
        raise # Ponowne zgłoszenie błędu do głównego bloku try-except

def upload_attachment_to_jira(issue_id_or_key, filename, file_content):
    """Przesyła pojedynczy załącznik do zadania Jira."""
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN]):
        logging.error("Brak pełnych danych uwierzytelniających Jira. Nie można przesłać załącznika.")
        return False # Zwróć False zamiast rzucać wyjątek, aby kontynuować dla innych załączników

    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_id_or_key}/attachments"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {
        "X-Atlassian-Token": "no-check" # Wymagane przez Jira dla załączników
    }

    # Używamy io.BytesIO, aby traktować bajty pliku jako plik w pamięci
    files = {
        'file': (filename, io.BytesIO(file_content))
    }

    response = None
    try:
        response = requests.post(url, auth=auth, files=files, headers=headers)
        response.raise_for_status()
        logging.info(f"Załącznik '{filename}' dodany do zadania Jira {issue_id_or_key}.")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas przesyłania załącznika '{filename}' do Jira {issue_id_or_key}: {e}")
        if response is not None:
            logging.error(f"Odpowiedź Jira (załącznik BŁĄD): {response.text}")
        return False # Zwróć False, aby wskazać niepowodzenie

# --- ENDPOINT (Główna logika webhooka) ---
@app.route("/webhook", methods=["POST"])
def pipedrive_webhook():
    logging.info("Otrzymano żądanie webhooka Pipedrive.")
    try:
        request_data = request.json
        logging.info(f"Odebrano dane JSON z webhooka: {request_data}")

        # Oczekujemy, że webhook Pipedrive wyśle tylko deal_id i org_id
        deal_id = request_data.get("deal_id")
        org_id = request_data.get("org_id")

        if not deal_id or not org_id:
            logging.warning(f"Brak deal_id lub org_id w otrzymanym JSON: {request_data}. "
                            f"Oczekiwano {{'deal_id': ..., 'org_id': ...}}")
            return jsonify({"error": "Missing 'deal_id' or 'org_id' in JSON payload."}), 400

        logging.info(f"Pobieranie szczegółów dla deal_id: {deal_id}, org_id: {org_id} z Pipedrive API.")

        # Pobranie szczegółów deala z Pipedrive
        deal_data = get_deal_from_pipedrive(deal_id)
        if not deal_data:
            return jsonify({"error": f"Failed to retrieve deal {deal_id} from Pipedrive."}), 500

        # Pobranie szczegółów organizacji z Pipedrive
        org_data = get_organization_from_pipedrive(org_id)
        if not org_data:
            return jsonify({"error": f"Failed to retrieve organization {org_id} from Pipedrive."}), 500

        # --- PRZETWARZANIE POBRANYCH DANYCH ---
        # Pobieranie wartości pól niestandardowych z deala Pipedrive
        typ_prezentacji_pipedrive_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["typ_prezentacji_tech"])
        data_1_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["data_1"])
        data_2_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["data_2"])
        data_3_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["data_3"])

        # Pobieranie wartości pola 'partner' z obiektu organizacji Pipedrive
        raw_partner_data = org_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["partner_org_field"])
        # Sprawdzamy, czy to słownik i wyciągamy nazwę, w przeciwnym razie używamy wartości bez zmian
        partner_val = raw_partner_data.get('name') if isinstance(raw_partner_data, dict) else raw_partner_data

        logging.info(f"Pobrane wartości z Pipedrive (po przetworzeniu): "
                     f"Typ Prezentacji: {typ_prezentacji_pipedrive_val}, "
                     f"Data 1: {data_1_val}, Data 2: {data_2_val}, Data 3: {data_3_val}, "
                     f"Partner: {partner_val}")

        # Mapowanie 'Typ Prezentacji Technicznej' z Pipedrive ID na format Jira Option ID
        typ_prezentacji_tech_jira_format = []
        if typ_prezentacji_pipedrive_val:
            # Pipedrive dla pola typu 'set' zwraca listę ID, nawet jeśli jest tylko jeden wybrany
            # lub pojedyncze ID jako string (co było w Twoim poprzednim teście).
            # Zabezpieczamy się na oba przypadki:
            values_to_map = [str(typ_prezentacji_pipedrive_val)] if not isinstance(typ_prezentacji_pipedrive_val, list) else [str(v) for v in typ_prezentacji_pipedrive_val]

            for pid_option_id in values_to_map:
                jira_option = TYP_PREZENTACJI_MAPPING.get(pid_option_id)
                if jira_option:
                    typ_prezentacji_tech_jira_format.append(jira_option)
                else:
                    logging.warning(f"Nie znaleziono mapowania Jira dla Pipedrive ID '{pid_option_id}'. Opcja zostanie pominięta.")
        else:
            logging.info("Pole 'Typ Prezentacji Technicznej' z Pipedrive jest puste lub nie wybrane.")


        # Przygotowanie słownika pól do przekazania do funkcji create_jira_issue
        fields_for_jira_creation = {
            "deal_id": deal_id, # Użyte w description Jira
            "deal_title": deal_data.get("title"),
            "org_name": org_data.get("name"),
            "klient": org_data.get("name"), # Pole Klient w Jira
            "typ_prezentacji_tech_jira_format": typ_prezentacji_tech_jira_format,
            "data_1": data_1_val,
            "data_2": data_2_val,
            "data_3": data_3_val,
            "partner": partner_val # Teraz to powinien być czysty tekst lub None
        }

        # --- TWORZENIE ZADANIA W JIRA ---
        jira_creation_response = create_jira_issue(fields_for_jira_creation)
        jira_issue_key = jira_creation_response.get('key')
        jira_issue_id = jira_creation_response.get('id')

        # --- PRZESYŁANIE ZAŁĄCZNIKÓW DO JIRA ---
        if jira_issue_key:
            logging.info(f"Pobieranie załączników dla deala {deal_id} z Pipedrive...")
            pipedrive_attachments = get_attachments_from_pipedrive(deal_id)

            if pipedrive_attachments:
                logging.info(f"Znaleziono {len(pipedrive_attachments)} załączników. Rozpoczynanie przesyłania do Jira {jira_issue_key}.")
                for attachment_info in pipedrive_attachments:
                    file_id = attachment_info.get('id')
                    file_name = attachment_info.get('file_name')

                    if file_id and file_name:
                        logging.info(f"Pobieranie pliku '{file_name}' (ID: {file_id}) z Pipedrive...")
                        file_content = download_file_content_from_pipedrive(file_id)

                        if file_content:
                            logging.info(f"Przesyłanie pliku '{file_name}' do zadania Jira {jira_issue_key}...")
                            upload_success = upload_attachment_to_jira(jira_issue_key, file_name, file_content)
                            if not upload_success:
                                logging.error(f"Nie udało się przesłać załącznika '{file_name}'.")
                        else:
                            logging.warning(f"Brak zawartości pliku '{file_name}' (ID: {file_id}). Prawdopodobnie plik pusty lub błąd pobierania.")
                    else:
                        logging.warning(f"Brak ID pliku lub nazwy dla załącznika w Pipedrive: {attachment_info}. Pomijanie.")
            else:
                logging.info(f"Brak załączników dla deala {deal_id} w Pipedrive.")
        else:
            logging.error("Nie uzyskano klucza/ID zadania Jira po utworzeniu. Nie można przesłać załączników.")

        logging.info("Zakończono przetwarzanie webhooka Pipedrive i utworzono zadanie Jira (oraz załączniki, jeśli były).")
        return jsonify(jira_creation_response), 201

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 500
        error_message = e.response.text if e.response is not None else str(e)
        logging.error(f"Błąd HTTP podczas przetwarzania webhooka: Status {status_code}, Wiadomość: {error_message}", exc_info=True)
        return jsonify({"error": f"HTTP Error: {status_code} - {error_message}"}), status_code
    except Exception as e:
        logging.error(f"Wystąpił nieoczekiwany błąd podczas przetwarzania webhooka: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# --- Uruchomienie aplikacji (dla Render.com używany jest Gunicorn, lokalnie Flask) ---
if __name__ == "__main__":
    # Render.com udostępnia port poprzez zmienną środowiskową PORT
    port = int(os.environ.get("PORT", 5000))
    # Uruchomienie aplikacji w trybie debugowania (tylko do rozwoju, nie na produkcję)
    app.run(host="0.0.0.0", port=port, debug=True)
