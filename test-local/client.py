import hashlib
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

SERVEUR = "http://127.0.0.1:8765"
TAILLE_BLOC = 1024 * 1024
TAILLE_MAX = 50 * 1024 * 1024


def calculer_sha256(chemin):
    empreinte = hashlib.sha256()

    with chemin.open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(TAILLE_BLOC), b""):
            empreinte.update(bloc)

    return empreinte.hexdigest()


def requete_http(url, donnees=None, entetes=None, methode=None):
    requete = urllib.request.Request(
        url,
        data=donnees,
        headers=entetes or {},
        method=methode,
    )

    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return reponse.read().decode("utf-8")


def main():
    if len(sys.argv) != 2:
        print("Utilisation : python3 client.py <fichier>")
        return

    chemin = Path(sys.argv[1]).expanduser()

    if not chemin.is_file():
        print("Erreur : fichier introuvable.")
        return

    taille = chemin.stat().st_size

    if taille > TAILLE_MAX:
        print("Erreur : limite de 50 Mio dépassée.")
        return

    empreinte = calculer_sha256(chemin)

    print(f"Fichier : {chemin.name}")
    print(f"Taille : {taille} octets")
    print(f"SHA-256 : {empreinte}")

    confirmation = input("Envoyer ce fichier au serveur local ? (o/N) ")
    if confirmation.strip().lower() != "o":
        print("Envoi annulé.")
        return

    identifiant = None

    try:
        # 1. Demander au serveur de préparer le transfert.
        metadonnees = json.dumps({
            "nom": chemin.name,
            "taille": taille,
            "sha256": empreinte,
        }).encode("utf-8")

        identifiant = requete_http(
            f"{SERVEUR}/start",
            donnees=metadonnees,
            entetes={"Content-Type": "application/json"},
            methode="POST",
        ).strip()

        # 2. Envoyer les blocs un par un.
        with chemin.open("rb") as fichier:
            numero = 0

            while True:
                bloc = fichier.read(TAILLE_BLOC)
                if not bloc:
                    break

                requete_http(
                    f"{SERVEUR}/upload",
                    donnees=bloc,
                    entetes={
                        "Content-Type": "application/octet-stream",
                        "X-Transfer-ID": identifiant,
                        "X-Block-Number": str(numero),
                    },
                    methode="POST",
                )

                numero += 1
                envoyes = min(numero * TAILLE_BLOC, taille)
                print(
                    f"\rEnvoi : {envoyes}/{taille} octets",
                    end="",
                    flush=True,
                )

        # 3. Demander la vérification finale.
        resultat = requete_http(
            f"{SERVEUR}/finish",
            entetes={"X-Transfer-ID": identifiant},
            methode="POST",
        )

        print("\n\nRéponse du serveur :")
        print(resultat)

        empreinte_recue = next(
            (
                ligne.split(":", 1)[1].strip()
                for ligne in resultat.splitlines()
                if ligne.startswith("SHA-256 :")
            ),
            None,
        )

        if empreinte_recue == empreinte:
            print("VÉRIFICATION RÉUSSIE : fichier reçu intact.")
        else:
            print("ERREUR : empreintes différentes.")

    except urllib.error.HTTPError as erreur:
        print(f"\nErreur HTTP {erreur.code} : {erreur.reason}")
    except (urllib.error.URLError, TimeoutError, OSError) as erreur:
        print(f"\nÉchec du transfert : {erreur}")
    except UnicodeDecodeError:
        print("\nErreur : réponse serveur invalide.")


if __name__ == "__main__":
    main()