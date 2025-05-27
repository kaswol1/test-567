import os
import requests
import json

# --- KONFIGURACJA ---
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN") # Uzupełnij
JIRA_EMAIL = os.getenv("JIRA_EMAIL")     # Uzupełnij
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN") 

PROJECT_KEY = "RQIMP"
ISSUE_TYPE_NAME = "Task"

# --- FUNKCJA POBIERAJĄCA METADANE ---
def get_jira_createmeta():
    if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN]):
        print("BŁĄD: Brak pełnych danych uwierzytelniających Jira. Proszę je uzupełnić.")
        return None

    url = (
        f"https://{JIRA_DOMAIN}/rest/api/3/issue/createmeta?"
        f"projectKeys={PROJECT_KEY}&issueTypeNames={ISSUE_TYPE_NAME}&expand=projects.issuetypes.fields"
    )
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}

    print(f"Pobieranie metadanych z: {url}")
    try:
        response = requests.get(url, headers=headers, auth=auth)
        response.raise_for_status() # Wyrzuca wyjątek dla statusów 4xx/5xx
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas pobierania metadanych Jira: {e}")
        if response is not None:
            print(f"Odpowiedź Jira: {response.text}")
        return None

# --- ANALIZA ODPOWIEDZI ---
if __name__ == "__main__":
    createmeta_data = get_jira_createmeta()

    if createmeta_data:
        print("\n--- Analiza pól dla projektu RQIMP i typu zadania Task ---")
        projects = createmeta_data.get('projects', [])
        found_fields = False
        for project in projects:
            if project.get('key') == PROJECT_KEY:
                issue_types = project.get('issueTypes', [])
                for issue_type in issue_types:
                    if issue_type.get('name') == ISSUE_TYPE_NAME:
                        fields = issue_type.get('fields', {})
                        if fields:
                            found_fields = True
                            print(f"\nZnaleziono pola dla projektu '{PROJECT_KEY}' i typu zadania '{ISSUE_TYPE_NAME}':")
                            for field_id, field_details in fields.items():
                                field_name = field_details.get('name')
                                is_required = field_details.get('required')
                                schema_type = field_details.get('schema', {}).get('type')
                                schema_custom = field_details.get('schema', {}).get('custom') # Np. 'com.atlassian.servicedesk...'
                                schema_custom_id = field_details.get('schema', {}).get('customId')
                                allowed_values = field_details.get('allowedValues')

                                print(f"\n  ID pola: {field_id}")
                                print(f"    Nazwa: {field_name}")
                                print(f"    Wymagane: {is_required}")
                                print(f"    Typ schematu: {schema_type}")
                                if schema_custom:
                                    print(f"    Custom Type: {schema_custom}")
                                if schema_custom_id:
                                    print(f"    Custom ID: {schema_custom_id}")
                                if allowed_values:
                                    print("    Dozwolone wartości (dla pól wyboru):")
                                    for option in allowed_values:
                                        print(f"      - Value: {option.get('value')}, ID: {option.get('id')}")
                                # Dodatkowe logowanie dla pola Request Type (jeśli jest)
                                if schema_custom and "request-type" in schema_custom:
                                    print(f"    *** TO JEST POLE REQUEST TYPE! Customfield ID: {field_id} ***")
                                    print(f"    Potrzebujemy przekazać ID opcji dla tego pola.")

                        break # Zakończ po znalezieniu pól dla Task
                break # Zakończ po znalezieniu Task w projekcie
        if not found_fields:
            print(f"Nie znaleziono szczegółów pól dla projektu '{PROJECT_KEY}' i typu zadania '{ISSUE_TYPE_NAME}'.")
            print("Upewnij się, że klucz projektu i nazwa typu zadania są poprawne.")

    print("\n--- KONIEC ANALIZY ---")
    print("Proszę, prześlij mi całą wygenerowaną sekcję dla pola 'Request Type' (jeśli się pojawi) oraz listę WSZYSTKICH pól oznaczonych jako 'Wymagane: True'.")
