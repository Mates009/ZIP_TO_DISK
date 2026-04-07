import shutil
import zipfile
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import pickle # Modul pro ukládání a načítání ověřovacího tokenu pro Google

# Knihovny pro Google Drive API
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

# --- KONSTANTY PRO GOOGLE DRIVE ---
# Práva, která náš program vyžaduje (plný přístup k disku)
SCOPES = ['https://www.googleapis.com/auth/drive']
# ID tvé cílové složky z odkazu
TARGET_FOLDER_ID = '1QkOreWB8mzWujJ2wbkcW06tYb7I97BeT'

class ZipApp:
    def __init__(self, master):
        self.master = master
        master.title("Nástroj pro Zazipování a Nahrání na GDrive")
        master.geometry("600x300")
        master.resizable(False, False)

        self.style = ttk.Style()
        self.style.theme_use('alt')

        # Výběr souborů/složek
        self.source_paths_label = ttk.Label(master, text="Vybrané soubory/složky k zazipování:")
        self.source_paths_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.source_paths_text = tk.Text(master, height=4, width=50, state='disabled')
        self.source_paths_text.grid(row=0, column=1, padx=10, pady=5, sticky="w")

        self.add_button = ttk.Button(master, text="Přidat soubor(y)/složku(y)", command=self.add_source_paths)
        self.add_button.grid(row=0, column=2, padx=10, pady=5)

        self.clear_button = ttk.Button(master, text="Vyčistit seznam", command=self.clear_source_paths)
        self.clear_button.grid(row=1, column=2, padx=10, pady=5)

        self.selected_paths = []

        # Výstupní ZIP soubor (dočasně se uloží do PC, pak se pošle na disk)
        self.output_zip_label = ttk.Label(master, text="Dočasná cesta pro lokální ZIP:")
        self.output_zip_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")

        self.output_zip_entry = ttk.Entry(master, width=50)
        self.output_zip_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        self.browse_output_zip_button = ttk.Button(master, text="Uložit lokálně jako", command=self.browse_output_zip)
        self.browse_output_zip_button.grid(row=2, column=2, padx=10, pady=5)

        # Spouštěcí tlačítko
        self.zip_button = ttk.Button(master, text="Spustit zazipování a nahrát na Disk", command=self.start_zipping_thread)
        self.zip_button.grid(row=3, column=0, columnspan=3, pady=20)

        # Progress bar a stavy
        self.progress_label = ttk.Label(master, text="Průběh:")
        self.progress_label.grid(row=4, column=0, padx=10, pady=5, sticky="w")

        self.progress_bar = ttk.Progressbar(master, orient="horizontal", length=400, mode="determinate")
        self.progress_bar.grid(row=4, column=1, columnspan=2, padx=10, pady=5, sticky="ew")
        
        self.status_label = ttk.Label(master, text="Připraveno.")
        self.status_label.grid(row=5, column=0, columnspan=3, padx=10, pady=5, sticky="w")

        master.grid_columnconfigure(1, weight=1)

    def add_source_paths(self):
        response = messagebox.askyesno("Vybrat", "Chcete přidat SLOŽKU? (Ne pro přidání SOUBORŮ)")
        if response:
            path = filedialog.askdirectory(title="Vyberte složku k zazipování")
            if path:
                self.add_to_selected_paths(path)
        else:
            paths = filedialog.askopenfilenames(
                title="Vyberte soubory k zazipování",
                filetypes=(("Všechny soubory", "*.*"), ("Textové soubory", "*.txt"))
            )
            if paths:
                for path in paths:
                    self.add_to_selected_paths(path)

    def add_to_selected_paths(self, path):
        if path and path not in self.selected_paths:
            self.selected_paths.append(path)
            self.update_source_paths_display()

    def clear_source_paths(self):
        self.selected_paths.clear()
        self.update_source_paths_display()

    def update_source_paths_display(self):
        self.source_paths_text.config(state='normal')
        self.source_paths_text.delete(1.0, tk.END)
        for path in self.selected_paths:
            self.source_paths_text.insert(tk.END, path + "\n")
        self.source_paths_text.config(state='disabled')

    def browse_output_zip(self):
        filename = filedialog.asksaveasfilename(
            title="Uložit lokální ZIP soubor jako",
            defaultextension=".zip",
            filetypes=(("Zip soubory", "*.zip"), ("Všechny soubory", "*.*"))
        )
        if filename:
            self.output_zip_entry.delete(0, tk.END)
            self.output_zip_entry.insert(0, filename)

    def start_zipping_thread(self):
        self.zip_button.config(state=tk.DISABLED)
        self.status_label.config(text="Probíhá zazipování...")
        self.progress_bar['value'] = 0

        zipping_thread = threading.Thread(target=self.perform_zipping)
        zipping_thread.start()

    def perform_zipping(self):
        output_zip_name = self.output_zip_entry.get()
        source_paths = self.selected_paths

        if not source_paths:
            messagebox.showerror("Chyba", "Prosím, přidejte soubory nebo složky k zazipování.")
            self.reset_gui()
            return

        if not output_zip_name:
            messagebox.showerror("Chyba", "Prosím, zadejte lokální cílovou cestu pro dočasný ZIP soubor.")
            self.reset_gui()
            return

        try:
            total_items = len(source_paths)
            processed_items = 0

            # 1. ČÁST: VYTVOŘENÍ ZIPU
            with zipfile.ZipFile(output_zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for i, item_path in enumerate(source_paths):
                    if not os.path.exists(item_path):
                        self.update_status(f"Upozornění: '{item_path}' nebyla nalezena.")
                        processed_items += 1
                        continue

                    if os.path.isdir(item_path):
                        for root, dirs, files in os.path.walk(item_path):
                            for file in files:
                                file_full_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_full_path, os.path.dirname(item_path))
                                zipf.write(file_full_path, arcname)
                    elif os.path.isfile(item_path):
                        zipf.write(item_path, os.path.basename(item_path))

                    processed_items += 1
                    progress_value = (processed_items / total_items) * 100
                    self.master.after(0, lambda p=progress_value: self.progress_bar.config(value=p))

            self.update_status(f"ZIP vytvořen lokálně. Zahajuji nahrávání na Google Drive...")

            # 2. ČÁST: NAHRÁNÍ NA GOOGLE DRIVE
            creds = None
            # Načtení existujícího tokenu (pokud ses už dříve přihlásil)
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            
            # Pokud token není nebo expiroval, vyžádáme nový
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                # Uložíme si token pro příště
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)

            # Připojení k Google API
            service = build('drive', 'v3', credentials=creds)

            # Metadata souboru (jméno a do jaké složky má jít)
            file_metadata = {
                'name': os.path.basename(output_zip_name),
                'parents': [TARGET_FOLDER_ID]
            }
            
            # Nahrajeme soubor
            media = MediaFileUpload(output_zip_name, resumable=True)
            self.update_status("Nahrávám ZIP na Google Drive. Prosím čekejte...")
            
            uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            # Hotovo
            self.update_status(f"Kompletní! ZIP uložen lokálně a nahrán na Disk.")
            messagebox.showinfo("Úspěch", "Soubory byly úspěšně zazipovány a nahrány na Google Drive!")

        except Exception as e:
            messagebox.showerror("Chyba", f"Došlo k chybě: {e}")
            self.update_status(f"Chyba: {e}")
        finally:
            self.reset_gui()

    def update_status(self, message):
        self.master.after(0, lambda: self.status_label.config(text=message))

    def reset_gui(self):
        self.master.after(0, lambda: self.zip_button.config(state=tk.NORMAL))
        self.master.after(0, lambda: self.status_label.config(text="Připraveno."))
        self.master.after(0, lambda: self.progress_bar.config(value=0))

if __name__ == "__main__":
    root = tk.Tk()
    app = ZipApp(root)
    root.mainloop()