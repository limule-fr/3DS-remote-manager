from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import hashlib
import json
import re
import time
import uuid

HOST = "127.0.0.1"
PORT = 8765

DOSSIER_RECU = Path(__file__).parent / "recu"
DOSSIER_TEMP = Path(__file__).parent / "temp"

TAILLE_BLOC = 1024 * 1024
TAILLE_MAX = 2 * 1024 * 1024 * 1024
DUREE_MAX = 3600

# Transferts temporaires en mémoire : identifiant -> métadonnées.
transferts = {}


def reponse(handler, code, message):
    donnees = message.encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(donnees)))
    handler.end_headers()
    handler.wfile.write(donnees)


class Serveur(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            reponse(self, 404, "Route inconnue")
            return

        reponse(self, 200, "3DS Remote Manager - serveur opérationnel")

    def do_POST(self):
        if self.path == "/start":
            self.demarrer_transfert()
        elif self.path == "/upload":
            self.recevoir_bloc()
        elif self.path == "/finish":
            self.terminer_transfert()
        else:
            reponse(self, 404, "Route inconnue")

    def lire_json(self):
        try:
            taille = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= taille <= 4096:
                return None
            donnees = self.rfile.read(taille)
            return json.loads(donnees.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def demarrer_transfert(self):
        infos = self.lire_json()
        if not isinstance(infos, dict):
            reponse(self, 400, "Requête invalide")
            return

        nom = infos.get("nom")
        taille = infos.get("taille")
        empreinte = infos.get("sha256")

        if (
            not isinstance(nom, str)
            or not nom
            or nom in {".", ".."}
            or Path(nom).name != nom
            or not isinstance(taille, int)
            or isinstance(taille, bool)
            or not 0 <= taille <= TAILLE_MAX
            or not isinstance(empreinte, str)
            or not re.fullmatch(r"[0-9a-f]{64}", empreinte)
        ):
            reponse(self, 400, "Métadonnées invalides")
            return

        identifiant = uuid.uuid4().hex
        DOSSIER_TEMP.mkdir(parents=True, exist_ok=True)
        chemin_temp = DOSSIER_TEMP / f"{identifiant}.part"

        try:
            chemin_temp.touch(exist_ok=False)
        except OSError:
            reponse(self, 500, "Impossible de préparer le transfert")
            return

        nombre_blocs = (taille + TAILLE_BLOC - 1) // TAILLE_BLOC

        transferts[identifiant] = {
            "nom": nom,
            "taille": taille,
            "sha256": empreinte,
            "nombre_blocs": nombre_blocs,
            "prochain_bloc": 0,
            "chemin": chemin_temp,
            "debut": time.monotonic(),
        }

        reponse(self, 201, identifiant)

    def recevoir_bloc(self):
        identifiant = self.headers.get("X-Transfer-ID", "")
        transfert = transferts.get(identifiant)

        if transfert is None:
            reponse(self, 404, "Transfert inconnu")
            return

        if time.monotonic() - transfert["debut"] > DUREE_MAX:
            self.abandonner(identifiant)
            reponse(self, 408, "Transfert expiré")
            return

        try:
            numero = int(self.headers.get("X-Block-Number", "-1"))
            taille = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            reponse(self, 400, "En-têtes invalides")
            return

        attendu = transfert["prochain_bloc"]
        restant = transfert["taille"] - attendu * TAILLE_BLOC
        taille_attendue = min(TAILLE_BLOC, restant)

        if numero != attendu or taille != taille_attendue:
            reponse(self, 400, "Bloc inattendu ou taille incorrecte")
            return

        bloc = self.rfile.read(taille)
        if len(bloc) != taille:
            self.abandonner(identifiant)
            reponse(self, 400, "Bloc incomplet")
            return

        try:
            with transfert["chemin"].open("ab") as fichier:
                fichier.write(bloc)
        except OSError:
            self.abandonner(identifiant)
            reponse(self, 500, "Erreur d'écriture")
            return

        transfert["prochain_bloc"] += 1
        reponse(self, 200, "Bloc reçu")

    def terminer_transfert(self):
        identifiant = self.headers.get("X-Transfer-ID", "")
        transfert = transferts.get(identifiant)

        if transfert is None:
            reponse(self, 404, "Transfert inconnu")
            return

        if time.monotonic() - transfert["debut"] > DUREE_MAX:
            self.abandonner(identifiant)
            reponse(self, 408, "Transfert expiré")
            return

        if transfert["prochain_bloc"] != transfert["nombre_blocs"]:
            reponse(self, 400, "Transfert incomplet")
            return

        empreinte = hashlib.sha256()
        taille_reelle = 0

        try:
            with transfert["chemin"].open("rb") as fichier:
                for bloc in iter(
                    lambda: fichier.read(TAILLE_BLOC), b""
                ):
                    empreinte.update(bloc)
                    taille_reelle += len(bloc)
        except OSError:
            self.abandonner(identifiant)
            reponse(self, 500, "Impossible de vérifier le fichier")
            return

        if (
            taille_reelle != transfert["taille"]
            or empreinte.hexdigest() != transfert["sha256"]
        ):
            self.abandonner(identifiant)
            reponse(self, 422, "Échec de vérification SHA-256")
            return

        destination = DOSSIER_RECU / transfert["nom"]

        # Ne jamais écraser un fichier déjà présent.
        try:
            with destination.open("xb") as sortie:
                with transfert["chemin"].open("rb") as source:
                    while True:
                        bloc = source.read(TAILLE_BLOC)
                        if not bloc:
                            break
                        sortie.write(bloc)
        except FileExistsError:
            reponse(self, 409, "Ce fichier existe déjà")
            return
        except OSError:
            destination.unlink(missing_ok=True)
            reponse(self, 500, "Erreur lors de la finalisation")
            return

        self.abandonner(identifiant)
        reponse(
            self,
            201,
            f"Reçu : {destination.name}\n"
            f"Taille : {taille_reelle} octets\n"
            f"SHA-256 : {empreinte.hexdigest()}\n",
        )

    def abandonner(self, identifiant):
        transfert = transferts.pop(identifiant, None)
        if transfert:
            transfert["chemin"].unlink(missing_ok=True)

    def log_message(self, format, *args):
        print("[HTTP]", format % args, flush=True)


if __name__ == "__main__":
    DOSSIER_RECU.mkdir(parents=True, exist_ok=True)
    DOSSIER_TEMP.mkdir(parents=True, exist_ok=True)

    serveur = HTTPServer((HOST, PORT), Serveur)
    print(f"Serveur actif sur http://{HOST}:{PORT}")
    print(f"Réception : {DOSSIER_RECU}")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
    finally:
        serveur.server_close()
