from flask import Flask, request, jsonify
import requests
import os
import logging
import io

# --- KONFIGURACJA APLIKACJI FLASK ---
app = Flask(__name__)

# --- KONFIGURACJA LOGOWANIA ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- KONFIGURACJA DANYCH DOSTĘPOWYCH API (ZMIENNE ŚRODOWISKOWE Z RENDER.COM) ---
PIPEDRIVE_API_TOKEN = os.getenv("PIPEDRIVE_API_TOKEN")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN") # Np. twojafirma.atlassian.net

# Sprawdzenie, czy wszystkie kluczowe zmienne środowiskowe są ustawione
if not PIPEDRIVE_API_TOKEN:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa PIPEDRIVE_API_TOKEN nie jest ustawiona.")
if not JIRA_API_TOKEN:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa JIRA_API_TOKEN nie jest ustawiona.")
if not JIRA_EMAIL:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa JIRA_EMAIL nie jest ustawiona.")
if not JIRA_DOMAIN:
    logging.error("BŁĄD KONFIGURACJI: Zmienna środowiskowa JIRA_DOMAIN nie jest ustawiona. Np. 'yourcompany.atlassian.net'")

# --- KONFIGURACJA PROJEKTU JIRA ---
# Używamy ID projektu zamiast klucza, zgodnie z ostatnimi ustaleniami.
JIRA_PROJECT_ID = "43" # <-- Zmieniono z klucza na ID projektu!
JIRA_ISSUE_TYPE = "Zadanie" # Używamy polskiej nazwy.

# --- MAPOWANIE PÓL NIESTANDARDOWYCH ---

PIPEDRIVE_CUSTOM_FIELDS_HASHES = {
    "typ_prezentacji_tech": "5bc985e61592b58e001c657305423499b6a23ce4",
    "data_1": "77554ed03246265be68e75bc152243b19d492d9f",
    "data_2": "348bc2d5699beb5a76ae34f9318055a0bbbef3a8",
    "data_3": "db137c6e874446aaa7e42d1638538f5138786633",
    "partner_org_field": "fea50f9d3ff5801b5fa9c451a8110445442db46d",
    "notatka_summary": "b1d7a6fb7866d3e88f0eb486ae1032012bf8295b" # Klucz Pipedrive dla Notatki (Summary)
}

JIRA_CUSTOM_FIELDS_IDS = {
    "typ_prezentacji_tech": "customfield_1008",
    "klient": "customfield_10086",
    "data_1": "customfield_10090",
    "data_2": "customfield_10089",
    "data_3": "customfield_10091",
    "partner": "customfield_10092",
    "request_type_field": "customfield_10010" # ID pola "Request Type" dla Jira Service Management
}

# --- KONFIGURACJA WARTOŚCI DLA POLA "REQUEST TYPE" (customfield_10010) ---
# TA WARTOŚĆ JEST KLUCZOWA. Prawdopodobnie będzie to ID opcji, np. {"id": "10002"}.
# PONIEWAŻ NIE UDAŁO NAM SIĘ TEGO WYCIĄGNĄĆ Z LOGÓW, UŻYWAMY TERAZ PLACEHOLDERU
# Z ZAAKŁADANYM FORMATEM. JEŚLI BĘDZIE BŁĄD, BĘDZIE TO WYNIKAŁO Z TEJ WARTOŚCI.
JIRA_REQUEST_TYPE_VALUE = {"value": "YOUR_EXACT_REQUEST_TYPE_NAME_FROM_JIRA_LOGS"} # <-- Nadal wymaga uzupełnienia!


# Mapowanie opcji dla pola 'Typ Prezentacji Technicznej'
TYP_PREZENTACJI_MAPPING = {
    "32": {"id": "32"}, # Prezentacja wprowadzająca
    "33": {"id": "33"}, # Prezentacja techniczna
    "68": {"id": "68"}, # PoC
    "69": {"id": "69"}, # Demo
    "70": {"id": "70"}, # Rozmowa referencyjna
}

# --- FUNKCJA DO LOGOWANIA METADANYCH CREATEMETA (WYWOŁYWANA RAZ PRZY STARCIE) ---
def log_jira_createmeta_details():
    """Pobiera i loguje szczegóły pól wymaganych oraz opcji dla Request Type."""
    logging.info("Rozpoczynam pobieranie metadanych Jira createmeta...")
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN]):
        logging.error("Brak pełnych danych uwierzytelniających Jira do pobrania metadanych (API_TOKEN, EMAIL, DOMAIN). Pomijam funkcję log_jira_createmeta_details.")
        return

    url = (
        f"https://{JIRA_DOMAIN}/rest/api/3/issue/createmeta?"
        f"projectIds={JIRA_PROJECT_ID}&issueTypeNames={JIRA_ISSUE_TYPE}&expand=projects.issuetypes.fields" # Używamy projectIds!
    )
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, auth=auth)
        response.raise_for_status()
        createmeta_data = response.json()

        projects = createmeta_data.get('projects', [])
        
        found_project = False
        found_issue_type = False

        for project in projects:
            # Sprawdzamy po ID projektu, a nie po kluczu
            if str(project.get('id')) == JIRA_PROJECT_ID: 
                found_project = True
                issue_types = project.get('issueTypes', [])
                for issue_type in issue_types:
                    if issue_type.get('name') == JIRA_ISSUE_TYPE:
                        found_issue_type = True
                        fields = issue_type.get('fields', {})
                        logging.info(f"\n--- METADANE PÓL DLA PROJEKTU (ID: {JIRA_PROJECT_ID}) I TYPU ZADANIA '{JIRA_ISSUE_TYPE}' ---")
                        
                        required_fields_info = {}
                        request_type_field_details_found = None

                        for field_id, field_details in fields.items():
                            field_name = field_details.get('name')
                            is_required = field_details.get('required')
                            schema_custom = field_details.get('schema', {}).get('custom')
                            
                            if is_required:
                                required_fields_info[field_id] = field_name

                            if field_id == JIRA_CUSTOM_FIELDS_IDS["request_type_field"]:
                                request_type_field_details_found = field_details
                                
                        if required_fields_info:
                            logging.info("--- POLA WYMAGANE (required: true) ---")
                            for f_id, f_name in required_fields_info.items():
                                logging.info(f"  - ID: {f_id}, Nazwa: {f_name}")
                        else:
                            logging.info("Brak pól oznaczonych jako 'wymagane: true' w metadanych dla tego typu zadania.")

                        if request_type_field_details_found:
                            logging.info(f"\n--- SZCZEGÓŁY POLA REQUEST TYPE ({JIRA_CUSTOM_FIELDS_IDS['request_type_field']}) ---")
                            logging.info(f"  Nazwa pola: {request_type_field_details_found.get('name')}")
                            logging.info(f"  Typ Schematu: {request_type_field_details_found.get('schema', {}).get('type')}")
                            logging.info(f"  Custom Type: {request_type_field_details_found.get('schema', {}).get('custom')}")
                            logging.info(f"  Custom ID: {request_type_field_details_found.get('schema', {}).get('customId')}")

                            if request_type_field_details_found.get('allowedValues'):
                                logging.info("  Dostępne opcje (allowedValues) dla pola Request Type:")
                                for option in request_type_field_details_found['allowedValues']:
                                    # TE LINIE SĄ KLUCZOWE - TUTAJ BĘDZIESZ SZUKAĆ PRAWIDŁOWEJ WARTOŚCI DLA JIRA_REQUEST_TYPE_VALUE
                                    logging.info(f"    - Value: '{option.get('value')}', ID: '{option.get('id')}'")
                            else:
                                logging.info("  Brak dostępnych opcji (allowedValues) dla tego pola Request Type. Może być polem tekstowym lub innym.")
                        else:
                            logging.warning(f"Nie znaleziono pola Request Type o ID '{JIRA_CUSTOM_FIELDS_IDS['request_type_field']}' w metadanych dla typu zadania '{JIRA_ISSUE_TYPE}'.")
                        
                        logging.info("\n--- KONIEC METADANYCH CREATEMETA ---")
                        return # Zakończ po znalezieniu i zalogowaniu

        if not found_project:
            logging.error(f"Projekt (ID: {JIRA_PROJECT_ID}) nie został znaleziony w metadanych Jira createmeta.")
        elif not found_issue_type:
            logging.error(f"Typ zadania '{JIRA_ISSUE_TYPE}' nie został znaleziony w projekcie (ID: {JIRA_PROJECT_ID}) w metadanych Jira createmeta.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Błąd podczas pobierania metadanych Jira createmeta (sprawdź JIRA_DOMAIN, EMAIL, API_TOKEN, uprawnienia): {e}")
        if response is not None:
            logging.error(f"Odpowiedź Jira: {response.text}")
    except Exception as e:
        logging.error(f"Nieoczekiwany błąd podczas analizy metadanych Jira: {e}", exc_info=True)


# --- FUNKCJE POMOCNICZE (KOMUNIKACJA Z API) ---
def get_deal_from_pipedrive(deal_id):
    """Pobiera szczegóły deala z Pipedrive."""
    if not PIPEDRIVE_API_TOKEN:
        logging.error("PIPEDRIVE_API_TOKEN nie jest ustawiony.")
        return None
    url = f"https://api.pipedrive.com/v1/deals/{deal_id}?api_token={PIPEDRIVE_API_TOKEN}"
    try:
        response = requests.get(url)
        response.raise_for_status()
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
        return response.json().get("data", [])
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
        response = requests.get(url, stream=True)
        response.raise_for_status()
        return response.content
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

    jira_issue_payload = {
        "fields": {
            "project": {"id": JIRA_PROJECT_ID}, # <--- Używamy ID projektu 43!
            "summary": fields_to_create.get("summary_notatka", "Nowy deal Pipedrive (brak notatki)"),
            "description": f"Organizacja: {fields_to_create.get('org_name', 'Brak nazwy organizacji')}\n"
                           f"Deal ID: {fields_to_create.get('deal_id', 'Brak ID deala')}",
            "issuetype": {"name": JIRA_ISSUE_TYPE},
        }
    }

    # === DODANIE POLA "REQUEST TYPE" DLA JIRA SERVICE MANAGEMENT (customfield_10010) ===
    # Wartość jest pobierana z JIRA_REQUEST_TYPE_VALUE, którą UZUPEŁNISZ PO ODCZYTANIU LOGÓW.
    if JIRA_CUSTOM_FIELDS_IDS["request_type_field"]:
        jira_issue_payload["fields"][JIRA_CUSTOM_FIELDS_IDS["request_type_field"]] = JIRA_REQUEST_TYPE_VALUE
    else:
        logging.warning("ID pola 'Request Type' nie jest zdefiniowane w konfiguracji.")


    # Dodawanie pozostałych pól niestandardowych tylko, jeśli mają wartości
    # customfield_1008: Typ Prezentacji Technicznej (multi-select w Jira)
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

    # Pola dat (tekstowe, format incessantly-MM-DD)
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
        response.raise_for_status()
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
        return False

    url = f"https://{JIRA_DOMAIN}/rest/api/3/issue/{issue_id_or_key}/attachments"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {
        "X-Atlassian-Token": "no-check"
    }

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
        return False

# --- ENDPOINT (Główna logika webhooka) ---
@app.route("/webhook", methods=["POST"])
def pipedrive_webhook():
    logging.info("Otrzymano żądanie webhooka Pipedrive.")
    try:
        request_data = request.json
        logging.info(f"Odebrano dane JSON z webhooka: {request_data}")

        deal_id = request_data.get("deal_id")
        org_id = request_data.get("org_id")

        if not deal_id or not org_id:
            logging.warning(f"Brak deal_id lub org_id w otrzymanym JSON: {request_data}. "
                            f"Oczekiwano {{'deal_id': ..., 'org_id': ...}}")
            return jsonify({"error": "Missing 'deal_id' or 'org_id' in JSON payload."}), 400

        logging.info(f"Pobieranie szczegółów dla deal_id: {deal_id}, org_id: {org_id} z Pipedrive API.")

        deal_data = get_deal_from_pipedrive(deal_id)
        if not deal_data:
            return jsonify({"error": f"Failed to retrieve deal {deal_id} from Pipedrive."}), 500

        org_data = get_organization_from_pipedrive(org_id)
        if not org_data:
            return jsonify({"error": f"Failed to retrieve organization {org_id} from Pipedrive."}), 500

        # --- PRZETWARZANIE POBRANYCH DANYCH ---
        typ_prezentacji_pipedrive_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["typ_prezentacji_tech"])
        data_1_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["data_1"])
        data_2_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["data_2"])
        data_3_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["data_3"])
        notatka_summary_val = deal_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["notatka_summary"])

        raw_partner_data = org_data.get(PIPEDRIVE_CUSTOM_FIELDS_HASHES["partner_org_field"])
        partner_val = None
        if raw_partner_data is None:
            logging.info("Pole 'Partner' z Pipedrive jest puste (None).")
        elif isinstance(raw_partner_data, dict):
            partner_val = raw_partner_data.get('name')
            logging.info(f"Pole 'Partner' z Pipedrive to słownik. Pobrano nazwę: {partner_val}")
        elif isinstance(raw_partner_data, (str, int, float)):
            partner_val = str(raw_partner_data)
            logging.info(f"Pole 'Partner' z Pipedrive to prosty typ. Wartość: {partner_val}")
        else:
            partner_val = str(raw_partner_data)
            logging.warning(f"Pole 'Partner' z Pipedrive ma nieoczekiwany typ ({type(raw_partner_data)}). Próba konwersji na string: {partner_val}")

        logging.info(f"Pobrane wartości z Pipedrive (po przetworzeniu): "
                     f"Typ Prezentacji: {typ_prezentacji_pipedrive_val}, "
                     f"Data 1: {data_1_val}, Data 2: {data_2_val}, Data 3: {data_3_val}, "
                     f"Partner: {partner_val} (Typ: {type(partner_val)}), "
                     f"Notatka (Summary): {notatka_summary_val}")

        typ_prezentacji_tech_jira_format = []
        if typ_prezentacji_pipedrive_val:
            values_to_map = [str(typ_prezentacji_pipedrive_val)] if not isinstance(typ_prezentacji_pipedrive_val, list) else [str(v) for v in typ_prezentacji_pipedrive_val]
            for pid_option_id in values_to_map:
                jira_option = TYP_PREZENTACJI_MAPPING.get(pid_option_id)
                if jira_option:
                    typ_prezentacji_tech_jira_format.append(jira_option)
                else:
                    logging.warning(f"Nie znaleziono mapowania Jira dla Pipedrive ID '{pid_option_id}'. Opcja zostanie pominięta.")
        else:
            logging.info("Pole 'Typ Prezentacji Technicznej' z Pipedrive jest puste lub nie wybrane.")

        # --- Przygotowanie słownika pól do przekazania do funkcji create_jira_issue ---
        fields_for_jira_creation = {
            "deal_id": deal_id,
            "summary_notatka": notatka_summary_val,
            "org_name": org_data.get("name"),
            "klient": org_data.get("name"),
            "typ_prezentacji_tech_jira_format": typ_prezentacji_tech_jira_format,
            "data_1": data_1_val,
            "data_2": data_2_val,
            "data_3": data_3_val,
            "partner": partner_val
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
                logging.info(f"Znaleziono {len(pipedrive_attachments)} załączników dla deala {deal_id}. Rozpoczynanie przesyłania do Jira {jira_issue_key}.")
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
@app.route("/health") # Dodatkowy endpoint do sprawdzania statusu aplikacji
def health_check():
    return "OK", 200

if __name__ == "__main__":
    # Wywołaj funkcję logującą metadane Jira przy starcie aplikacji
    # Daje to wgląd w wymagane pola i opcje Request Type w logach.
    logging.info("Aplikacja startuje. Logowanie metadanych Jira createmeta...")
    log_jira_createmeta_details()
    logging.info("Logowanie metadanych zakończone. Aplikacja gotowa do odbierania webhooków.")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
