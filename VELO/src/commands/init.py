import requests


def run_init(args):
    url = "https://media.ilevia.fr/opendata/station_status.json"

    try:
        response = requests.get(url, timeout=10)

        response.raise_for_status()

        data = response.json()

        print("Connexion réussie")
        print(
            f"Nombre de stations : {len(data['data']['stations'])}"
        )

    except requests.exceptions.RequestException as e:
        print(f"Erreur : {e}")