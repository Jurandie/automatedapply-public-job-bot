from __future__ import annotations

import contextlib
import io
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.config import DEFAULT_DB_PATH, DEFAULT_PROFILE_PATH, PROJECT_ROOT
from app.main import main as cli_main
from app.runtime_control import (
    is_paused,
    request_pause,
    request_stop,
    reset_run_control,
    resume_run,
)


APP_TITLE = "Automated Apply"
BG = "#0f172a"
PANEL = "#111827"
PANEL_ALT = "#172033"
TEXT = "#e5e7eb"
MUTED = "#94a3b8"
ACCENT = "#14b8a6"
ACCENT_DARK = "#0f766e"
WARNING = "#f59e0b"
DANGER = "#ef4444"
BORDER = "#253044"


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, width: int = 430):
        super().__init__(parent, style="Root.TFrame")
        self.canvas = tk.Canvas(
            self,
            bg=BG,
            highlightthickness=0,
            bd=0,
            width=width,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="Root.TFrame")
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.inner.bind("<Enter>", self._bind_mousewheel)
        self.inner.bind("<Leave>", self._unbind_mousewheel)

    def _on_inner_configure(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_mousewheel(self, _event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class AutomatedApplyGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x760")
        self.minsize(980, 680)
        self.configure(bg=BG)

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.db_path = tk.StringVar(value=str(DEFAULT_DB_PATH))
        self.profile_path = tk.StringVar(value=str(DEFAULT_PROFILE_PATH))
        self.ratings_path = tk.StringVar(value=str(PROJECT_ROOT / "data" / "company_ratings.yaml"))
        self.mode = tk.StringVar(value="fill_only")
        self.limit = tk.StringVar(value="1")
        self.status_filter = tk.StringVar(value="")
        self.use_claude = tk.BooleanVar(value=False)
        self.headless = tk.BooleanVar(value=False)
        self.skip_glassdoor_gate = tk.BooleanVar(value=False)
        self.max_posts = tk.StringVar(value="50")
        self.browser_mode = tk.StringVar(value="chrome")
        self.cdp_url = tk.StringVar(value="http://127.0.0.1:9222")
        self.status_text = tk.StringVar(value="Pronto")
        self.pause_button_text = tk.StringVar(value="Pausar bot")

        self._configure_style()
        self._build_layout()
        self.after(120, self._drain_log_queue)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, bordercolor=BORDER)
        style.configure("Root.TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL, borderwidth=1, relief="solid")
        style.configure("Alt.TFrame", background=PANEL_ALT)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("PanelTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 12, "bold"))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Body.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground="#0b1220", foreground=TEXT, insertcolor=TEXT, borderwidth=1)
        style.configure("TCombobox", fieldbackground="#0b1220", foreground=TEXT, arrowcolor=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", "#0b1220")], foreground=[("readonly", TEXT)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#06211f", font=("Segoe UI", 10, "bold"), padding=10)
        style.map("Accent.TButton", background=[("active", "#2dd4bf"), ("disabled", "#334155")])
        style.configure("Secondary.TButton", background="#1f2937", foreground=TEXT, font=("Segoe UI", 10), padding=9)
        style.map("Secondary.TButton", background=[("active", "#334155"), ("disabled", "#1f2937")])
        style.configure("Danger.TButton", background=DANGER, foreground="#210606", font=("Segoe UI", 10, "bold"), padding=9)
        style.map("Danger.TButton", background=[("active", "#f87171")])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", PANEL)])

    def _build_layout(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=20)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="Automated Apply", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Controle local para buscar vagas em sites de empresas, revisar oportunidades, adaptar curriculos e preparar aplicacoes com seguranca.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        content = ttk.Frame(root, style="Root.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=0, minsize=390)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left_scroll = ScrollableFrame(content, width=430)
        left_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left = left_scroll.inner
        right = ttk.Frame(content, style="Root.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_config_panel(left)
        self._build_actions_panel(left)
        self._build_log_panel(right)
        self._build_footer(root)

    def _build_config_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        panel.pack(fill="x", pady=(0, 14))
        ttk.Label(panel, text="Configuracao", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(
            panel,
            text="Caminhos e limites usados pelo fluxo principal.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        self._path_row(panel, "Banco SQLite", self.db_path, [("SQLite", "*.sqlite3 *.sqlite *.db"), ("Todos", "*.*")])
        self._path_row(panel, "Perfil", self.profile_path, [("YAML", "*.yaml *.yml"), ("Todos", "*.*")])
        self._path_row(panel, "Notas Glassdoor", self.ratings_path, [("YAML", "*.yaml *.yml"), ("Todos", "*.*")])

        options = ttk.Frame(panel, style="Panel.TFrame")
        options.pack(fill="x", pady=(10, 0))
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="Modo", style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        mode = ttk.Combobox(
            options,
            textvariable=self.mode,
            values=("dry_run", "fill_only", "review_first", "auto_submit_safe"),
            state="readonly",
            width=18,
        )
        mode.grid(row=0, column=1, sticky="ew")

        ttk.Label(options, text="Limite", style="Body.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(options, textvariable=self.limit, width=8).grid(row=1, column=1, sticky="w", pady=(8, 0))

        ttk.Label(options, text="Max vagas", style="Body.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(options, textvariable=self.max_posts, width=8).grid(row=2, column=1, sticky="w", pady=(8, 0))

        ttk.Label(options, text="Navegador", style="Body.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        browser = ttk.Combobox(
            options,
            textvariable=self.browser_mode,
            values=("chrome", "cdp", "chromium"),
            state="readonly",
            width=18,
        )
        browser.grid(row=3, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(options, text="CDP URL", style="Body.TLabel").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Entry(options, textvariable=self.cdp_url).grid(row=4, column=1, sticky="ew", pady=(8, 0))

        checks = ttk.Frame(panel, style="Panel.TFrame")
        checks.pack(fill="x", pady=(12, 0))
        ttk.Checkbutton(checks, text="Usar Claude para casos ambiguos", variable=self.use_claude).pack(anchor="w")
        ttk.Checkbutton(checks, text="Rodar browser em headless", variable=self.headless).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            checks,
            text="Ignorar filtro Glassdoor nesta execucao",
            variable=self.skip_glassdoor_gate,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            checks,
            text="Padrao: Google Chrome instalado. Para usar uma janela aberta, clique em 'Abrir Chrome controlavel' e selecione navegador=cdp.",
            style="Muted.TLabel",
            wraplength=330,
        ).pack(anchor="w", pady=(8, 0))

    def _build_actions_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        panel.pack(fill="x")
        ttk.Label(panel, text="Fluxo", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(
            panel,
            text="Use o fluxo completo para buscar vagas e preencher somente as elegiveis.",
            style="Muted.TLabel",
            wraplength=330,
        ).pack(anchor="w", pady=(2, 12))

        self._button(panel, "Abrir Chrome controlavel", self.open_controlled_chrome, "Secondary.TButton")
        self._button(panel, "Buscar e preencher elegiveis", self.scan_and_apply_jobs, "Accent.TButton")
        self._button(panel, "Revisar vagas encontradas", self.review_jobs, "Secondary.TButton")

        ttk.Label(panel, text="Controle", style="PanelTitle.TLabel").pack(anchor="w", pady=(10, 8))
        self._button(panel, "Pausar bot", self.pause_bot, "Secondary.TButton", textvariable=self.pause_button_text)
        self._button(panel, "Parar bot", self.stop_bot, "Danger.TButton")

        ttk.Label(panel, text="Ferramentas", style="PanelTitle.TLabel").pack(anchor="w", pady=(10, 8))
        self._button(panel, "Buscar vagas sem preencher", self.scan_company_sites, "Secondary.TButton")
        self._button(panel, "Verificar notas Glassdoor", self.check_company_ratings, "Secondary.TButton")
        self._button(panel, "Preencher vagas ja prontas", self.apply_jobs, "Secondary.TButton")
        self._button(panel, "Gerar curriculos adaptados", self.tailor_resumes, "Secondary.TButton")
        self._button(panel, "Salvar links das vagas", self.export_job_links, "Secondary.TButton")
        self._button(panel, "Relatorio", self.report, "Secondary.TButton")
        self._button(panel, "Inicializar banco", self.init_db, "Secondary.TButton")
        self._button(panel, "Abrir pasta de resultados", self.open_runtime_folder, "Secondary.TButton")

        warning = ttk.Label(
            panel,
            text="O bot preenche formularios, mas nao envia candidaturas automaticamente nesta versao.",
            style="Muted.TLabel",
            wraplength=330,
        )
        warning.pack(anchor="w", pady=(12, 0))

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Root.TFrame")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="Console do bot", style="Title.TLabel", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="Limpar log", style="Secondary.TButton", command=self.clear_log).grid(row=0, column=1, sticky="e")

        log_frame = ttk.Frame(parent, style="Panel.TFrame", padding=1)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log = tk.Text(
            log_frame,
            bg="#070b12",
            fg="#d1d5db",
            insertbackground=TEXT,
            selectbackground=ACCENT_DARK,
            relief="flat",
            padx=14,
            pady=14,
            wrap="word",
            font=("Cascadia Mono", 10),
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.tag_configure("info", foreground="#d1d5db")
        self.log.tag_configure("success", foreground="#5eead4")
        self.log.tag_configure("error", foreground="#fca5a5")
        self.log.tag_configure("muted", foreground=MUTED)
        self._append_log(
            "Pronto. Use 'Buscar e preencher elegiveis' para executar o fluxo principal.",
            "muted",
        )

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent, style="Root.TFrame")
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(footer, textvariable=self.status_text, style="Status.TLabel").pack(side="left")
        ttk.Label(footer, text=f"Workspace: {PROJECT_ROOT}", style="Status.TLabel").pack(side="right")

    def _path_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, filetypes) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 8))
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=label, style="Body.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(row, textvariable=variable).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(row, text="...", width=3, style="Secondary.TButton", command=lambda: self._browse_file(variable, filetypes)).grid(row=0, column=2)

    def _button(
        self,
        parent: ttk.Frame,
        text: str,
        command,
        style_name: str,
        textvariable: tk.StringVar | None = None,
    ) -> None:
        kwargs = {"text": text} if textvariable is None else {"textvariable": textvariable}
        ttk.Button(parent, command=command, style=style_name, **kwargs).pack(fill="x", pady=(0, 8))

    def _browse_file(self, variable: tk.StringVar, filetypes) -> None:
        path = filedialog.askopenfilename(initialdir=str(PROJECT_ROOT), filetypes=filetypes)
        if path:
            variable.set(path)

    def init_db(self) -> None:
        self._run_cli("Inicializar banco", ["--db", self.db_path.get(), "init-db"])

    def open_linkedin_login(self) -> None:
        self._run_cli(
            "Abrir LinkedIn / login",
            [
                "--db",
                self.db_path.get(),
                "open-linkedin-login",
                "--browser",
                self.browser_mode.get(),
                "--cdp-url",
                self.cdp_url.get(),
            ],
        )

    def open_controlled_chrome(self) -> None:
        self.browser_mode.set("cdp")
        self._run_cli(
            "Abrir Chrome controlavel",
            ["--db", self.db_path.get(), "open-controlled-chrome", "--port", "9222"],
        )

    def scan_from_file(self) -> None:
        sample_path = str(PROJECT_ROOT / "data" / "sample_posts.json")
        args = ["--db", self.db_path.get(), "scan-json", "--from-file", sample_path]
        if self.use_claude.get():
            args.append("--use-claude")
        self._run_cli("Scan por arquivo JSON", args)

    def scan_linkedin(self) -> None:
        args = [
            "--db",
            self.db_path.get(),
            "scan-linkedin-posts",
            "--max-posts",
            self.max_posts.get(),
            "--browser",
            self.browser_mode.get(),
            "--cdp-url",
            self.cdp_url.get(),
        ]
        if self.use_claude.get():
            args.append("--use-claude")
        if self.headless.get():
            args.append("--headless")
        self._run_cli("Scan LinkedIn real", args)

    def scan_company_sites(self) -> None:
        args = [
            "--db",
            self.db_path.get(),
            "scan-company-sites",
            "--max-jobs",
            self.max_posts.get(),
            "--browser",
            self.browser_mode.get(),
            "--cdp-url",
            self.cdp_url.get(),
        ]
        if self.use_claude.get():
            args.append("--use-claude")
        if self.headless.get():
            args.append("--headless")
        if self.skip_glassdoor_gate.get():
            args.append("--skip-glassdoor-gate")
        self._run_cli("Buscar vagas sem preencher", args)

    def check_company_ratings(self) -> None:
        args = [
            "--db",
            self.db_path.get(),
            "check-company-ratings",
            "--ratings-file",
            self.ratings_path.get(),
        ]
        self._run_cli("Verificar notas Glassdoor", args)

    def review_jobs(self) -> None:
        args = ["--db", self.db_path.get(), "review-jobs"]
        if self.status_filter.get().strip():
            args.extend(["--status", self.status_filter.get().strip()])
        self._run_cli("Revisar vagas encontradas", args)

    def tailor_resumes(self) -> None:
        args = ["--db", self.db_path.get(), "tailor-resumes", "--profile", self.profile_path.get()]
        limit = self.limit.get().strip()
        if limit:
            args.extend(["--limit", limit])
        self._run_cli("Gerar curriculos adaptados", args)

    def apply_jobs(self) -> None:
        args = [
            "--db",
            self.db_path.get(),
            "apply",
            "--mode",
            self.mode.get(),
            "--profile",
            self.profile_path.get(),
            "--browser",
            self.browser_mode.get(),
            "--cdp-url",
            self.cdp_url.get(),
        ]
        limit = self.limit.get().strip()
        if limit:
            args.extend(["--limit", limit])
        if self.headless.get():
            args.append("--headless")
        self._run_cli("Preencher vagas ja prontas", args)

    def scan_and_apply_jobs(self) -> None:
        args = [
            "--db",
            self.db_path.get(),
            "scan-and-apply",
            "--max-jobs",
            self.max_posts.get(),
            "--mode",
            self.mode.get(),
            "--profile",
            self.profile_path.get(),
            "--browser",
            self.browser_mode.get(),
            "--cdp-url",
            self.cdp_url.get(),
        ]
        limit = self.limit.get().strip()
        if limit:
            args.extend(["--limit", limit])
        if self.use_claude.get():
            args.append("--use-claude")
        if self.headless.get():
            args.append("--headless")
        if self.skip_glassdoor_gate.get():
            args.append("--skip-glassdoor-gate")
        self._run_cli("Buscar e preencher elegiveis", args)

    def report(self) -> None:
        self._run_cli("Relatorio", ["--db", self.db_path.get(), "report"])

    def export_job_links(self) -> None:
        args = ["--db", self.db_path.get(), "export-job-links", "--open-notepad"]
        if self.status_filter.get().strip():
            args.extend(["--status", self.status_filter.get().strip()])
        self._run_cli("Salvar links das vagas", args)

    def open_runtime_folder(self) -> None:
        runtime = PROJECT_ROOT / "data" / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        os.startfile(runtime)

    def pause_bot(self) -> None:
        if not self.worker or not self.worker.is_alive():
            self._append_log("Nenhuma operacao em execucao para pausar.", "muted")
            return
        if is_paused():
            resume_run()
            self.pause_button_text.set("Pausar bot")
            self.status_text.set("Executando")
            self._append_log("Bot retomado.", "success")
        else:
            request_pause()
            self.pause_button_text.set("Continuar bot")
            self.status_text.set("Pausado")
            self._append_log("Pausa solicitada. O bot vai parar no proximo checkpoint seguro.", "muted")

    def stop_bot(self) -> None:
        if not self.worker or not self.worker.is_alive():
            self._append_log("Nenhuma operacao em execucao para parar.", "muted")
            return
        request_stop()
        self.pause_button_text.set("Pausar bot")
        self.status_text.set("Parando")
        self._append_log("Parada solicitada. O bot vai encerrar no proximo checkpoint seguro.", "error")

    def clear_log(self) -> None:
        self.log.delete("1.0", "end")

    def _run_cli(self, title: str, args: list[str]) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "Uma operacao ja esta rodando. Aguarde terminar.")
            return
        reset_run_control()
        self.pause_button_text.set("Pausar bot")
        self.status_text.set(f"Executando: {title}")
        self._append_log(f"\n> {title}", "success")
        self._append_log(f"$ automatedapply {' '.join(args)}", "muted")
        self.worker = threading.Thread(target=self._worker, args=(title, args), daemon=True)
        self.worker.start()

    def _worker(self, title: str, args: list[str]) -> None:
        started = time.time()
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = 1
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = cli_main(args)
        except SystemExit as exc:
            exit_code = int(exc.code or 0) if isinstance(exc.code, int) else 1
        except Exception as exc:
            stderr.write(f"{type(exc).__name__}: {exc}\n")

        duration = time.time() - started
        out = stdout.getvalue().strip()
        err = stderr.getvalue().strip()
        if out:
            self.log_queue.put((out, "info"))
        if err:
            self.log_queue.put((err, "error"))
        if exit_code == 0:
            self.log_queue.put((f"{title} concluido em {duration:.1f}s.", "success"))
            self.log_queue.put(("__STATUS__Pronto", "muted"))
        elif exit_code == 130:
            self.log_queue.put((f"{title} interrompido em {duration:.1f}s.", "muted"))
            self.log_queue.put(("__STATUS__Interrompido", "muted"))
        else:
            self.log_queue.put((f"{title} falhou com codigo {exit_code}.", "error"))
            self.log_queue.put(("__STATUS__Erro", "error"))
        self.log_queue.put(("__PAUSE_TEXT__Pausar bot", "muted"))

    def _drain_log_queue(self) -> None:
        try:
            while True:
                message, tag = self.log_queue.get_nowait()
                if message.startswith("__STATUS__"):
                    self.status_text.set(message.replace("__STATUS__", "", 1))
                elif message.startswith("__PAUSE_TEXT__"):
                    self.pause_button_text.set(message.replace("__PAUSE_TEXT__", "", 1))
                else:
                    self._append_log(message, tag)
        except queue.Empty:
            pass
        self.after(120, self._drain_log_queue)

    def _append_log(self, message: str, tag: str = "info") -> None:
        self.log.insert("end", message + "\n", tag)
        self.log.see("end")


def main() -> int:
    app = AutomatedApplyGUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
