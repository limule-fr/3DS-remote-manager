import hashlib
import os
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox


CHUNK_SIZE = 1024 * 1024  # 1 Mio


class RemoteManager:
    def __init__(self, root):
        self.root = root
        self.root.title("3DS Remote Manager")
        self.root.geometry("650x480")
        self.root.minsize(550, 430)

        self.file_path = None
        self.file_hash = None

        self.filename = tk.StringVar(
            value="Aucun fichier sélectionné"
        )
        self.filesize = tk.StringVar(value="—")
        self.hash_value = tk.StringVar(value="—")
        self.status = tk.StringVar(value="En attente")

        self.build_interface()

    def build_interface(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="3DS REMOTE MANAGER",
            font=("Sans", 18, "bold")
        ).pack(pady=(0, 5))

        ttk.Label(
            main,
            text="Transfert de fichiers vers une Nintendo 3DS"
        ).pack(pady=(0, 20))

        ttk.Separator(main).pack(fill="x", pady=5)

        ttk.Label(
            main,
            text="Fichier sélectionné :",
            font=("Sans", 10, "bold")
        ).pack(anchor="w", pady=(12, 3))

        ttk.Label(
            main,
            textvariable=self.filename,
            wraplength=580
        ).pack(anchor="w")

        ttk.Label(
            main,
            text="Taille du fichier :"
        ).pack(anchor="w", pady=(12, 3))

        ttk.Label(
            main,
            textvariable=self.filesize
        ).pack(anchor="w")

        ttk.Label(
            main,
            text="Empreinte SHA-256 :",
            font=("Sans", 10, "bold")
        ).pack(anchor="w", pady=(12, 3))

        ttk.Label(
            main,
            textvariable=self.hash_value,
            wraplength=580
        ).pack(anchor="w")

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=20)

        ttk.Button(
            buttons,
            text="Choisir un fichier",
            command=self.choose_file
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            buttons,
            text="Calculer SHA-256",
            command=self.calculate_hash
        ).pack(side="left")

        ttk.Button(
            main,
            text="Préparer le transfert",
            command=self.prepare_transfer
        ).pack(fill="x", pady=(0, 12))

        ttk.Separator(main).pack(fill="x")

        ttk.Label(
            main,
            textvariable=self.status
        ).pack(anchor="w", pady=(10, 0))

        ttk.Label(
            main,
            text="Version 0.1 — Transfert distant non activé",
            font=("Sans", 9)
        ).pack(anchor="w", pady=(5, 0))

    def choose_file(self):
        # Vérifier que Zenity est installé.
        if shutil.which("zenity") is None:
            messagebox.showerror(
                "Zenity introuvable",
                "Le sélecteur de fichiers nécessite Zenity.\n\n"
                "Installe-le avec :\n"
                "sudo apt install zenity"
            )
            return

        try:
            result = subprocess.run(
                [
                    "zenity",
                    "--file-selection",
                    "--title=Ouvrir les fichiers",
                    "--file-filter=Tous les fichiers | *"
                ],
                capture_output=True,
                text=True,
                check=False
            )

        except OSError as error:
            messagebox.showerror(
                "Erreur",
                f"Impossible d'ouvrir le sélecteur :\n{error}"
            )
            return

        # L'utilisateur a annulé la sélection.
        if result.returncode != 0:
            return

        path = result.stdout.strip()

        if not path:
            return

        try:
            if not os.path.isfile(path):
                messagebox.showwarning(
                    "Fichier invalide",
                    "Le chemin sélectionné ne correspond pas "
                    "à un fichier valide."
                )
                return

            size = os.path.getsize(path)

        except OSError as error:
            messagebox.showerror(
                "Erreur de lecture",
                f"Impossible d'accéder au fichier :\n{error}"
            )
            return

        self.file_path = path
        self.file_hash = None

        self.filename.set(os.path.basename(path))
        self.filesize.set(
            f"{size:,} octets ({size / 1024 / 1024:.2f} Mio)"
        )
        self.hash_value.set("Non calculée")
        self.status.set("Fichier sélectionné")

    def calculate_hash(self):
        if not self.file_path:
            messagebox.showwarning(
                "Aucun fichier",
                "Sélectionne d'abord un fichier."
            )
            return

        try:
            digest = hashlib.sha256()

            with open(self.file_path, "rb") as file:
                while True:
                    chunk = file.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    digest.update(chunk)

            self.file_hash = digest.hexdigest()
            self.hash_value.set(self.file_hash)
            self.status.set("Empreinte calculée")

        except OSError as error:
            self.file_hash = None
            self.hash_value.set("Erreur de calcul")

            messagebox.showerror(
                "Erreur de lecture",
                f"Impossible de lire le fichier :\n{error}"
            )

    def prepare_transfer(self):
        if not self.file_path:
            messagebox.showwarning(
                "Aucun fichier",
                "Sélectionne d'abord un fichier."
            )
            return

        if not self.file_hash:
            self.calculate_hash()

            if not self.file_hash:
                return

        accepted = messagebox.askyesno(
            "Attention — Transfert de fichier",
            f"Fichier : {os.path.basename(self.file_path)}\n"
            f"Taille : {self.filesize.get()}\n\n"
            "Un fichier provenant d'une source inconnue "
            "peut être dangereux.\n\n"
            "SHA-256 vérifie l'intégrité, mais ne garantit "
            "pas que le fichier est sans virus.\n\n"
            "Vérifie que tu es autorisé à transférer ce fichier.\n\n"
            "Souhaites-tu continuer ?"
        )

        if not accepted:
            self.status.set("Transfert annulé")
            return

        messagebox.showinfo(
            "Transfert non disponible",
            "Aucun fichier n'a été envoyé.\n\n"
            "L'interface fonctionne ! Le transfert distant "
            "sera ajouté dans une prochaine version."
        )

        self.status.set(
            "Fichier prêt — transfert à développer"
        )


def main():
    root = tk.Tk()
    RemoteManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()