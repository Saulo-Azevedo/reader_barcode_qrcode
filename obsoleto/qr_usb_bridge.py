import tkinter as tk
from tkinter import ttk
import threading
import time
from datetime import datetime
import requests
from collections import defaultdict, deque

# DEFAULT_API_URL = "https://web-production-fd2d9.up.railway.app/api/registrar-leitura/"
DEFAULT_API_URL = " "
DEFAULT_OPERADOR = "NOTE-SAULO-USB"
DEFAULT_DEDUP_MS = 4000

def normalize_keyboard_layout(s: str) -> str:
    """
    Normaliza bugs comuns de layout de teclado em scanner HID (PT-BR/US).
    Ex.: 'httpsÇ;;' ou 'httpsç;;' -> 'https://'
    Também corrige alguns caracteres que costumam aparecer no lugar de '/', ':'.
    """
    # Mapeamento simples e efetivo para os seus casos reais
    return (
        s.replace("ç", ":")
         .replace("Ç", ":")
         .replace(";", "/")
    )

def is_probably_ok(code: str) -> bool:
    """
    Heurística bem permissiva:
    - se contém o domínio esperado, considera OK
    - senão, ainda pode ser barcode/base64 — aceita se for "limpo" e razoável
    (A ideia é NÃO travar/descartar tudo. Só evitar lixo óbvio.)
    """
    c = code.strip()
    if len(c) < 3:
        return False

    low = c.lower()
    if "minhabotija.fogas.com.br" in low:
        return True

    # Aceita tokens/barcodes sem espaço e sem caracteres de controle
    if any(ch.isspace() for ch in c):
        return False

    # Evita strings muito "estranhas" (muitos símbolos aleatórios)
    # (bem leve: permite + / = _ - etc)
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:/._-+=?&%")
    strange = sum(1 for ch in c if ch not in allowed)
    if strange > 6:  # tolerância
        return False

    return True


class QRUsbBridgeApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("QR/Barcode USB → API (Django)")
        self.root.geometry("1220x700")

        # Estado
        self.running = False
        self.last_seen_at = {}          # code -> monotonic ms (dedup)
        self.counts = defaultdict(int)  # code -> count
        self.row_index = {}             # code -> idx (ordem do primeiro aparecimento)
        self.next_idx = 1

        # Fila de envio
        self.queue = deque()
        self.queue_lock = threading.Lock()
        self.sender_thread = None
        self.stop_sender = threading.Event()

        # Buffer oculto (pra não bagunçar o campo)
        self.scan_buffer = []
        self.last_key_ts = 0.0
        self.flush_after_id = None

        # Cooldown curto (reduz emenda sem deixar lento)
        self.capture_busy_until = 0.0

        # Config vars
        self.api_url_var = tk.StringVar(value=DEFAULT_API_URL)
        self.operador_var = tk.StringVar(value=DEFAULT_OPERADOR)
        self.dedup_ms_var = tk.StringVar(value=str(DEFAULT_DEDUP_MS))

        # UI
        self._build_ui()

        # ✅ Foco travado somente quando rodando
        self._keep_focus()

    # ---------------- UI ----------------
    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        top = ttk.LabelFrame(outer, text="Configuração")
        top.pack(fill="x")

        ttk.Label(top, text="API_URL:").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.api_entry = ttk.Entry(top, textvariable=self.api_url_var)
        self.api_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=6)

        ttk.Label(top, text="OPERADOR:").grid(row=0, column=2, sticky="w", padx=6, pady=6)
        self.op_entry = ttk.Entry(top, textvariable=self.operador_var, width=22)
        self.op_entry.grid(row=0, column=3, sticky="w", padx=6, pady=6)

        ttk.Label(top, text="DEDUP_MS:").grid(row=0, column=4, sticky="w", padx=6, pady=6)
        self.dedup_entry = ttk.Entry(top, textvariable=self.dedup_ms_var, width=8)
        self.dedup_entry.grid(row=0, column=5, sticky="w", padx=6, pady=6)

        self.btn_start = ttk.Button(top, text="▶ Iniciar", command=self.start)
        self.btn_start.grid(row=0, column=6, padx=6, pady=6)

        self.btn_stop = ttk.Button(top, text="■ Parar", command=self.stop, state="disabled")
        self.btn_stop.grid(row=0, column=7, padx=6, pady=6)

        self.status_var = tk.StringVar(value="Status: parado")
        ttk.Label(top, textvariable=self.status_var).grid(row=0, column=8, sticky="w", padx=12, pady=6)

        self.queue_var = tk.StringVar(value="Fila: 0")
        ttk.Label(top, textvariable=self.queue_var).grid(row=0, column=9, sticky="w", padx=12, pady=6)

        top.columnconfigure(1, weight=1)

        scan_box = ttk.LabelFrame(outer, text="Leitura")
        scan_box.pack(fill="x", pady=(10, 0))

        ttk.Label(scan_box, text="Aponte e leia. (ENTER finaliza a leitura do scanner):").pack(anchor="w", padx=6, pady=(6, 0))

        # Campo fica limpo: capturamos teclas e bloqueamos a inserção
        self.scan_entry = ttk.Entry(scan_box, font=("Segoe UI", 14))
        self.scan_entry.pack(fill="x", padx=6, pady=6)
        self.scan_entry.bind("<KeyPress>", self._on_keypress)

        mid = ttk.Frame(outer)
        mid.pack(fill="both", expand=True, pady=10)

        left = ttk.LabelFrame(mid, text="Tabela (leituras)")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        cols = ("idx", "codigo", "contagem", "ultimo_envio")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18)
        self.tree.heading("idx", text="#")
        self.tree.heading("codigo", text="Código (QR/Barcode)")
        self.tree.heading("contagem", text="Contagem")
        self.tree.heading("ultimo_envio", text="Último envio")

        self.tree.column("idx", width=50, anchor="center")
        self.tree.column("codigo", width=560, anchor="w")
        self.tree.column("contagem", width=90, anchor="center")
        self.tree.column("ultimo_envio", width=170, anchor="center")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        vsb.pack(side="right", fill="y", pady=6)

        btns = ttk.Frame(left)
        btns.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(btns, text="Limpar tabela", command=self._clear_table).pack(side="left")
        ttk.Button(btns, text="Copiar selecionado", command=self._copy_selected).pack(side="left", padx=(8, 0))

        right = ttk.LabelFrame(mid, text="Log ao vivo")
        right.pack(side="right", fill="both", expand=True)

        self.log = tk.Text(right, height=18, font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    # ---------------- Focus handling ----------------
    def _keep_focus(self):
        # ✅ Rodando: trava o foco no campo de captura
        # ✅ Parado: deixa livre
        try:
            if self.running:
                self.scan_entry.focus_set()
        except Exception:
            pass
        self.root.after(250, self._keep_focus)

    # ---------------- Runtime ----------------
    def start(self):
        if self.running:
            return
        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set("Status: rodando (aguardando leituras)")
        self._log("✅ INICIADO. Foco travado no campo de leitura.")

        self.stop_sender.clear()
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_var.set("Status: parado")
        self._log("⏹ PARADO. Campos liberados. Não envia para API.")
        self.stop_sender.set()

    # ---------------- Keyboard capture ----------------
    def _on_keypress(self, event):
        # Cooldown curto (não deixa lento)
        now = time.time()
        if now < self.capture_busy_until:
            return "break"

        key = event.keysym
        ch = event.char or ""
        self.last_key_ts = now

        # ENTER finaliza
        if key in ("Return", "KP_Enter"):
            self._finalize_scan()
            return "break"

        # Backspace
        if key == "BackSpace":
            if self.scan_buffer:
                self.scan_buffer.pop()
            return "break"

        # ignora especiais sem char
        if not ch:
            return "break"

        self.scan_buffer.append(ch)

        # Flush por silêncio (bem curto, pra não atrasar)
        if self.flush_after_id is not None:
            try:
                self.root.after_cancel(self.flush_after_id)
            except Exception:
                pass

        # 70ms é suficiente pra scanners rápidos sem “sentir” lento
        self.flush_after_id = self.root.after(70, self._flush_if_idle)

        return "break"

    def _flush_if_idle(self):
        if time.time() - self.last_key_ts >= 0.07:
            self._finalize_scan()

    def _finalize_scan(self):
        if self.flush_after_id is not None:
            try:
                self.root.after_cancel(self.flush_after_id)
            except Exception:
                pass
            self.flush_after_id = None

        raw = "".join(self.scan_buffer).strip()
        self.scan_buffer = []

        if not raw:
            return

        # cooldown pequeno só pra não emendar dois scans colados
        self.capture_busy_until = time.time() + 0.04  # 40ms

        code = normalize_keyboard_layout(raw).strip()
        if code != raw:
            self._log(f"🔧 NORMALIZADO: {raw} -> {code}")

        # Dedup
        try:
            dedup_ms = int(self.dedup_ms_var.get().strip())
        except Exception:
            dedup_ms = DEFAULT_DEDUP_MS

        now_ms = int(time.monotonic() * 1000)
        last = self.last_seen_at.get(code)
        if last is not None and (now_ms - last) < dedup_ms:
            self._log(f"🟡 DEDUP: ignorado (< {dedup_ms}ms) | {code}")
            self._bump_table(code, sent_stamp="-")
            return
        self.last_seen_at[code] = now_ms

        # ✅ SEM DESCARTAR: sempre aparece na tabela
        self._log(f"📥 CAPTURADO: {code}")
        self._bump_table(code, sent_stamp="-")

        # Se parado, não envia
        if not self.running:
            self._log("⏸ (parado) não envia.")
            return

        # Só envia se parecer OK (evita poluir API com colisão evidente)
        if not is_probably_ok(code):
            self._log("🚫 SUSPEITO (provável cruzamento). Não enviou para API.")
            return

        with self.queue_lock:
            self.queue.append(code)
            qlen = len(self.queue)
        self.queue_var.set(f"Fila: {qlen}")

    # ---------------- Sender loop ----------------
    def _sender_loop(self):
        while not self.stop_sender.is_set():
            code = None
            with self.queue_lock:
                if self.queue:
                    code = self.queue.popleft()
                qlen = len(self.queue)
            self.root.after(0, lambda qlen=qlen: self.queue_var.set(f"Fila: {qlen}"))

            if not code:
                time.sleep(0.03)
                continue

            ok, status, detail = self._post_code(code)

            if ok:
                self.root.after(0, lambda c=code, s=status: self._on_api_ok(c, s))
            else:
                self.root.after(0, lambda c=code, st=status, d=detail: self._on_api_fail(c, st, d))
                # retry 1x
                time.sleep(0.20)
                with self.queue_lock:
                    self.queue.appendleft(code)
                    qlen2 = len(self.queue)
                self.root.after(0, lambda qlen2=qlen2: self.queue_var.set(f"Fila: {qlen2}"))
                time.sleep(0.50)

    def _post_code(self, code: str):
        url = self.api_url_var.get().strip()
        operador = self.operador_var.get().strip()

        payload = {
            "codigo": code,
            "origem": "qr",                                             
            "operador": operador,           
            "observacao": "qr_usb_pc",        # opcional (pode marcar que veio do leitor QR)
            # "origem": "qr_usb_pc",         
            # "tag_rfid": code,                 # <- obrigatório segundo sua doc
            # "operador": operador,             # opcional
        }


        headers = {"Content-Type": "application/json"}

        try:
            r = requests.post(url, json=payload, headers=headers, timeout=8)
            if 200 <= r.status_code < 300:
                return True, r.status_code, ""
            return False, r.status_code, (r.text or "")[:250]
        except Exception as e:
            return False, "EXC", str(e)

    def _on_api_ok(self, code: str, status_code: int):
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self._log(f"✅ ENVIADO OK ({status_code}): {code}")
        self._set_last_sent_stamp(code, ts)

    def _on_api_fail(self, code: str, status, detail: str):
        self._log(f"❌ ERRO envio | {code} | status={status} | {detail}")

    # ---------------- Table helpers ----------------
    def _bump_table(self, code: str, sent_stamp: str):
        self.counts[code] += 1
        count = self.counts[code]

        if code not in self.row_index:
            self.row_index[code] = self.next_idx
            self.next_idx += 1

        idx = self.row_index[code]

        iid = self._find_iid_by_code(code)
        if iid is None:
            self.tree.insert("", "end", values=(idx, code, count, sent_stamp))
        else:
            old = self.tree.item(iid, "values")
            last_stamp = old[3] if old and len(old) >= 4 else sent_stamp
            self.tree.item(iid, values=(idx, code, count, last_stamp))

    def _set_last_sent_stamp(self, code: str, stamp: str):
        iid = self._find_iid_by_code(code)
        if iid is None:
            if code not in self.row_index:
                self.row_index[code] = self.next_idx
                self.next_idx += 1
            idx = self.row_index[code]
            count = self.counts[code]
            self.tree.insert("", "end", values=(idx, code, count, stamp))
        else:
            vals = self.tree.item(iid, "values")
            if not vals:
                return
            self.tree.item(iid, values=(vals[0], vals[1], vals[2], stamp))

    def _find_iid_by_code(self, code: str):
        for iid in self.tree.get_children(""):
            vals = self.tree.item(iid, "values")
            if vals and vals[1] == code:
                return iid
        return None

    def _clear_table(self):
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        self.counts.clear()
        self.row_index.clear()
        self.last_seen_at.clear()
        self.next_idx = 1
        with self.queue_lock:
            self.queue.clear()
        self.queue_var.set("Fila: 0")
        self._log("🧹 Tabela/contadores/fila limpos.")

    def _copy_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if not vals:
            return
        code = vals[1]
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self._log(f"📋 Copiado: {code}")

    # ---------------- Logging ----------------
    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    QRUsbBridgeApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
