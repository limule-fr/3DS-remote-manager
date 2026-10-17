import hashlib
import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re


CHUNK_SIZE = 1024 * 1024  # 1 Mio


class RemoteManager:
    def __init__(self, root):
        self.root = root
        self.root.title("3DS Remote Manager")
        self.root.geometry("700x720")
        self.root.minsize(580, 500)

        self.file_path = None
        self.file_hash = None
        
        self.destination_root = tk.StringVar(value="")
        self.game_id = tk.StringVar(value="")

        self.cancel_event = threading.Event()
        self.operation_running = False

        self.filename = tk.StringVar(
            value="Aucun fichier sélectionné"
        )
        self.filesize = tk.StringVar(value="—")
        self.hash_value = tk.StringVar(value="—")
        self.status = tk.StringVar(value="En attente")
        self.progress_text = tk.StringVar(value="0 %")
        self.speed_text = tk.StringVar(value="Débit : —")
        self.remaining_text = tk.StringVar(
            value="Temps restant : —"
        )

        self.build_interface()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

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
            text="Gestionnaire de fichiers pour Nintendo 3DS"
        ).pack(pady=(0, 18))

        ttk.Separator(main).pack(fill="x", pady=5)

        target = ttk.LabelFrame(
            main,
            text="Destination de test",
            padding=10
        )
        target.pack(fill="x", pady=8)

        ttk.Label(
            target,
            text="Racine de destination :"
        ).pack(anchor="w")

        root_row = ttk.Frame(target)
        root_row.pack(fill="x", pady=4)

        ttk.Entry(
            root_row,
            textvariable=self.destination_root
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            root_row,
            text="Parcourir...",
            command=self.choose_destination_root
        ).pack(side="right", padx=(8, 0))

        ttk.Label(
            target,
            text="Identifiant du jeu (16 caractères hexadécimaux) :"
        ).pack(anchor="w", pady=(8, 2))

        ttk.Entry(
            target,
            textvariable=self.game_id,
            width=24
        ).pack(anchor="w")

        ttk.Button(
            target,
            text="Vérifier / créer le dossier",
            command=self.check_game_folder
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(
            main,
            text="Fichier sélectionné :",
            font=("Sans", 10, "bold")
        ).pack(anchor="w", pady=(12, 3))

        ttk.Label(
            main,
            textvariable=self.filename,
            wraplength=620
        ).pack(anchor="w")

        ttk.Label(
            main,
            text="Taille du fichier :"
        ).pack(anchor="w", pady=(10, 3))

        ttk.Label(
            main,
            textvariable=self.filesize
        ).pack(anchor="w")

        ttk.Label(
            main,
            text="Empreinte SHA-256 :",
            font=("Sans", 10, "bold")
        ).pack(anchor="w", pady=(10, 3))

        self.hash_entry = ttk.Entry(
            main,
            textvariable=self.hash_value,
            state="readonly"
        )
        self.hash_entry.pack(fill="x", pady=(0, 3))

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=16)

        self.choose_button = ttk.Button(
            buttons,
            text="Choisir un fichier",
            command=self.choose_file
        )
        self.choose_button.pack(side="left", padx=(0, 8))

        self.hash_button = ttk.Button(
            buttons,
            text="Calculer SHA-256",
            command=self.calculate_hash
        )
        self.hash_button.pack(side="left")

        ttk.Separator(main).pack(fill="x", pady=5)

        ttk.Label(
            main,
            text="Progression de l'opération :",
            font=("Sans", 10, "bold")
        ).pack(anchor="w", pady=(10, 5))

        progress_row = ttk.Frame(main)
        progress_row.pack(fill="x")

        self.progress = ttk.Progressbar(
            progress_row,
            mode="determinate",
            maximum=100,
            value=0
        )
        self.progress.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10)
        )

        ttk.Label(
            progress_row,
            textvariable=self.progress_text,
            width=7,
            anchor="e"
        ).pack(side="right")

        ttk.Label(
            main,
            textvariable=self.speed_text
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(
            main,
            textvariable=self.remaining_text
        ).pack(anchor="w", pady=(3, 0))

        self.prepare_button = ttk.Button(
            main,
            text="Préparer le transfert",
            command=self.prepare_transfer
        )
        self.prepare_button.pack(fill="x", pady=(16, 6))

        self.cancel_button = ttk.Button(
            main,
            text="Annuler l'opération",
            command=self.cancel_operation,
            state="disabled"
        )
        self.cancel_button.pack(fill="x", pady=(0, 12))

        ttk.Separator(main).pack(fill="x")

        ttk.Label(
            main,
            textvariable=self.status
        ).pack(anchor="w", pady=(10, 0))

        ttk.Label(
            main,
            text="Version 0.2 — Transfert distant non activé",
            font=("Sans", 9)
        ).pack(anchor="w", pady=(5, 0))

    def choose_destination_root(self):
        path = filedialog.askdirectory(
            title="Choisir la racine de destination"
        )

        if path:
            self.destination_root.set(path)
            self.status.set("Destination sélectionnée")

    def get_game_folder(self):
        game_id = self.game_id.get().strip().upper()

        if not re.fullmatch(r"[0-9A-F]{16}", game_id):
            messagebox.showwarning(
                "Identifiant invalide",
                "L'identifiant doit contenir exactement "
                "16 caractères hexadécimaux."
            )
            return None

        root = self.destination_root.get().strip()

        if not root or not os.path.isdir(root):
            messagebox.showwarning(
                "Destination invalide",
                "Sélectionne d'abord un dossier de destination."
            )
            return None

        return os.path.join(os.path.realpath(root), game_id)

    def check_game_folder(self):
        folder = self.get_game_folder()

        if folder is None:
            return

        if os.path.isdir(folder):
            messagebox.showinfo(
                "Dossier trouvé",
                f"Le dossier existe déjà :\n{folder}"
            )
            self.status.set("Dossier du jeu trouvé")
            return

        if os.path.exists(folder):
            messagebox.showerror("Erreur",
                "Un fichier portant ce nom existe déjà."
            )
            return

        accepted = messagebox.askyesno(
            "Créer le dossier",
            f"Ce dossier n'existe pas :\n{folder}\n\n"
            "Veux-tu le créer ?"
        )

        if not accepted:
            return

        try:
            os.makedirs(folder, exist_ok=False)

            messagebox.showinfo(
                "Dossier créé",
                f"Le dossier a été créé :\n{folder}"
            )
            self.status.set("Dossier du jeu créé")

        except OSError as error:
            messagebox.showerror(
                "Erreur",
                f"Impossible de créer le dossier :\n{error}"
            )   
    
    def set_busy(self, busy):
        self.operation_running = busy

        state = "disabled" if busy else "normal"
        self.choose_button.configure(state=state)
        self.hash_button.configure(state=state)
        self.prepare_button.configure(state=state)

        self.cancel_button.configure(
            state="normal" if busy else "disabled"
        )

    def reset_progress(self):
        self.progress.configure(value=0)
        self.progress_text.set("0 %")
        self.speed_text.set("Débit : —")
        self.remaining_text.set("Temps restant : —")

    def choose_file(self):
        if self.operation_running:
            return

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
        self.reset_progress()

    def calculate_hash(self):
        if self.operation_running:
            return

        if not self.file_path:
            messagebox.showwarning(
                "Aucun fichier",
                "Sélectionne d'abord un fichier."
            )
            return

        self.cancel_event.clear()
        self.set_busy(True)
        self.reset_progress()
        self.hash_value.set("Calcul en cours…")
        self.status.set("Calcul de SHA-256…")

        threading.Thread(
            target=self.hash_worker,
            daemon=True
        ).start()

    def hash_worker(self):
        started = time.monotonic()
        processed = 0
        digest = hashlib.sha256()

        try:
            total = os.path.getsize(self.file_path)

            with open(self.file_path, "rb") as file:
                while True:
                    if self.cancel_event.is_set():
                        self.root.after(
                            0,
                            lambda: self.finish_cancelled(
                                "Calcul SHA-256 annulé"
                            )
                        )
                        return

                    chunk = file.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    digest.update(chunk)
                    processed += len(chunk)

                    elapsed = max(time.monotonic() - started, 0.001)
                    speed = processed / elapsed
                    percent = (
                        processed / total * 100
                        if total > 0 else 100
                    )
                    remaining = (
                        (total - processed) / speed
                        if speed > 0 else 0
                    )

                    self.root.after(
                        0,
                        lambda p=percent, s=speed, r=remaining:
                            self.update_progress(p, s, r)
                    )

            result = digest.hexdigest()

            self.root.after(
                0,
                lambda: self.finish_hash(result)
            )

        except (OSError, ValueError) as error:
            self.root.after(
                0,
                lambda e=str(error): self.finish_error(
                    f"Erreur pendant le calcul : {e}"
                )
            )

    def update_progress(self, percent, speed, remaining):
        self.progress.configure(value=percent)
        self.progress_text.set(f"{percent:.1f} %")
        self.speed_text.set(
            f"Débit : {speed / 1024 / 1024:.2f} Mio/s"
        )

        if remaining >= 60:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            formatted = f"{minutes} min {seconds} s"
        else:
            formatted = f"{int(remaining)} s"

        self.remaining_text.set(
            f"Temps restant : {formatted}"
        )

    def finish_hash(self, result):
        if self.cancel_event.is_set():
            self.finish_cancelled("Calcul SHA-256 annulé")
            return

        self.file_hash = result
        self.hash_value.set(result)
        self.progress.configure(value=100)
        self.progress_text.set("100 %")
        self.remaining_text.set("Temps restant : 0 s")
        self.status.set("Empreinte SHA-256 calculée")
        self.set_busy(False)

    def finish_error(self, message):
        self.file_hash = None
        self.hash_value.set("Erreur de calcul")
        self.status.set("Erreur")
        self.set_busy(False)
        messagebox.showerror("Erreur", message)

    def cancel_operation(self):
        if self.operation_running:
            self.cancel_event.set()
            self.status.set("Annulation en cours…")
            self.cancel_button.configure(state="disabled")

    def finish_cancelled(self, message):
        self.file_hash = None
        self.hash_value.set("Calcul annulé")
        self.status.set(message)
        self.reset_progress()
        self.set_busy(False)

    def prepare_transfer(self):
        if self.operation_running:
            return

        if not self.file_path:
            messagebox.showwarning(
                "Aucun fichier",
                "Sélectionne d'abord un fichier."
            )
            return

        if not self.file_hash:
            messagebox.showinfo(
                "Empreinte nécessaire",
                "Calcule d'abord l'empreinte SHA-256.\n\n"
                "Tu pourras ensuite préparer le transfert."
            )
            self.calculate_hash()
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
            self.status.set("Préparation annulée")
            return

        messagebox.showinfo(
            "Transfert non disponible",
            "Aucun fichier n'a été envoyé.\n\n"
            "L'interface fonctionne. Le transfert distant "
            "sera ajouté dans une prochaine version."
        )

        self.status.set(
            "Fichier prêt — transfert à développer"
        )

    def close_app(self):
        if self.operation_running:
            accepted = messagebox.askyesno(
                "Quitter",
                "Une opération est en cours. "
                "Veux-tu l'annuler et quitter ?"
            )

            if not accepted:
                return

            self.cancel_event.set()

        self.root.destroy()


def main():
    root = tk.Tk()
    RemoteManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
