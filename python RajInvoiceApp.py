"""
Raj Pouch Packaging - Desktop Invoice Generator
------------------------------------------------
Desktop app using Tkinter + SQLite with PDF export (ReportLab).

Requirements (install once):
    pip install reportlab

Run:
    python RajInvoiceApp.py

Author: ChatGPT
"""

import os
import sqlite3
import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# PDF generation via ReportLab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


# ====== Company Constants (Auto-filled on every invoice) ======
COMPANY_NAME = "RAJ POUCH PACKAGING"
COMPANY_TAGLINE = "Manufacturer and Exporter of All Types of Packaging Machines"
COMPANY_ADDRESS = (
    "PLOT NO 30, SAI COMPLEX, B-BLOCK, WAZIRPUR ROAD,\n"
    "OLD FARIDABAD - 121002, HARYANA"
)
COMPANY_MOBILES = "Mobile: 7011568170, 8860244103"
COMPANY_EMAIL = "Email: babluthakur2012@gmail.com"

DB_FILE = "invoices.db"
OUTPUT_DIR = "invoices"


# ====== Data Models ======
@dataclass
class Item:
    name: str
    qty: float
    rate: float
    discount: float = 0.0  # absolute discount (₹) per line

    @property
    def amount(self) -> float:
        return max(0.0, self.qty * self.rate - self.discount)


@dataclass
class Invoice:
    invoice_no: str
    date: str  # YYYY-MM-DD
    customer_name: str
    customer_address: str
    customer_contact: str
    customer_gstin: str
    gst_rate: float  # percent
    notes: str
    items: List[Item]

    @property
    def subtotal(self) -> float:
        return sum(i.amount for i in self.items)

    @property
    def gst_amount(self) -> float:
        return round(self.subtotal * (self.gst_rate / 100.0), 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.gst_amount, 2)


# ====== Database Helpers ======
class InvoiceDB:
    def __init__(self, path: str = DB_FILE):
        self.path = path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_db(self):
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_no TEXT UNIQUE,
                    date TEXT,
                    customer_name TEXT,
                    customer_address TEXT,
                    customer_contact TEXT,
                    customer_gstin TEXT,
                    gst_rate REAL,
                    notes TEXT,
                    subtotal REAL,
                    gst_amount REAL,
                    total REAL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_no TEXT,
                    name TEXT,
                    qty REAL,
                    rate REAL,
                    discount REAL,
                    amount REAL,
                    FOREIGN KEY(invoice_no) REFERENCES invoices(invoice_no)
                )
                """
            )
            con.commit()

    def next_invoice_number(self) -> str:
        today = dt.date.today().strftime("%Y%m%d")
        prefix = f"INV-{today}-"
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("SELECT invoice_no FROM invoices WHERE invoice_no LIKE ? ORDER BY invoice_no DESC LIMIT 1", (f"{prefix}%",))
            row = cur.fetchone()
            if not row:
                return f"{prefix}0001"
            last = int(row[0].split("-")[-1])
            return f"{prefix}{last+1:04d}"

    def save_invoice(self, inv: Invoice):
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO invoices (
                    invoice_no, date, customer_name, customer_address,
                    customer_contact, customer_gstin, gst_rate, notes,
                    subtotal, gst_amount, total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inv.invoice_no,
                    inv.date,
                    inv.customer_name,
                    inv.customer_address,
                    inv.customer_contact,
                    inv.customer_gstin,
                    inv.gst_rate,
                    inv.notes,
                    inv.subtotal,
                    inv.gst_amount,
                    inv.total,
                ),
            )
            cur.execute("DELETE FROM items WHERE invoice_no=?", (inv.invoice_no,))
            for it in inv.items:
                cur.execute(
                    """
                    INSERT INTO items (invoice_no, name, qty, rate, discount, amount)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (inv.invoice_no, it.name, it.qty, it.rate, it.discount, it.amount),
                )
            con.commit()


# ====== PDF Generator ======
class PDFBuilder:
    def __init__(self, output_dir: str = OUTPUT_DIR):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def build(self, inv: Invoice, file_path: Optional[str] = None) -> str:
        if not file_path:
            safe_name = inv.invoice_no.replace("/", "-")
            file_path = os.path.join(self.output_dir, f"{safe_name}.pdf")

        doc = SimpleDocTemplate(file_path, pagesize=A4, rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
        styles = getSampleStyleSheet()
        story = []

        # Header
        title = f"<para align='center'><b>{COMPANY_NAME}</b></para>"
        story.append(Paragraph(title, styles['Title']))
        story.append(Paragraph(f"<para align='center'>{COMPANY_TAGLINE}</para>", styles['Normal']))
        story.append(Paragraph(f"<para align='center'>{COMPANY_ADDRESS}</para>", styles['Normal']))
        story.append(Paragraph(f"<para align='center'>{COMPANY_MOBILES} | {COMPANY_EMAIL}</para>", styles['Normal']))
        story.append(Spacer(1, 6))
        story.append(self._hr())

        # Invoice meta & customer block
        meta_data = [
            ["Invoice No:", inv.invoice_no, "Date:", inv.date],
            ["Customer:", inv.customer_name, "GST %:", f"{inv.gst_rate:.2f}%"],
            ["Contact:", inv.customer_contact, "GSTIN:", inv.customer_gstin or "-"],
        ]
        t_meta = Table(meta_data, colWidths=[25*mm, 70*mm, 20*mm, 60*mm])
        t_meta.setStyle(
            TableStyle([
                ('BOX', (0,0), (-1,-1), 0.5, colors.grey),
                ('INNERGRID', (0,0), (-1,-1), 0.25, colors.grey),
                ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ])
        )
        story.append(Spacer(1, 6))
        story.append(t_meta)
        story.append(Spacer(1, 8))

        # Items table
        data = [["S.No", "Item Description", "Qty", "Rate (₹)", "Discount (₹)", "Amount (₹)"]]
        for idx, it in enumerate(inv.items, start=1):
            data.append([
                str(idx),
                it.name,
                f"{it.qty:.2f}",
                f"{it.rate:.2f}",
                f"{it.discount:.2f}",
                f"{it.amount:.2f}",
            ])
        tbl = Table(data, colWidths=[12*mm, 75*mm, 18*mm, 25*mm, 28*mm, 30*mm])
        tbl.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('ALIGN', (2,1), (-1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8))

        # Totals
        totals_data = [
            ["Subtotal", f"₹ {inv.subtotal:.2f}"],
            [f"GST @ {inv.gst_rate:.2f}%", f"₹ {inv.gst_amount:.2f}"],
            ["Grand Total", f"₹ {inv.total:.2f}"],
        ]
        t_tot = Table(totals_data, colWidths=[90*mm, 98*mm])
        t_tot.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('FONTNAME', (0,2), (-1,2), 'Helvetica-Bold'),
        ]))
        story.append(t_tot)

        if inv.notes:
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"<b>Notes:</b> {inv.notes}", styles['Normal']))

        story.append(Spacer(1, 16))
        story.append(Paragraph("Authorized Signatory", styles['Normal']))

        doc.build(story)
        return file_path

    @staticmethod
    def _hr(height=0.5):
        tbl = Table([[" "]], colWidths=[180*mm], rowHeights=[height*mm])
        tbl.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.black)]))
        return tbl


# ====== Tkinter UI ======
class InvoiceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Raj Pouch Packaging - Invoice Generator")
        self.geometry("1050x700")
        self.minsize(980, 640)
        self.db = InvoiceDB()
        self.pdf = PDFBuilder()

        self._build_ui()
        self._reset_form(new_invoice=True)

    # ---- UI Layout ----
    def _build_ui(self):
        self.style = ttk.Style(self)
        self.style.configure("TButton", padding=6)
        self.style.configure("TLabel", padding=(2,2))
        self.style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))

        container = ttk.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        # Top - Company banner
        banner = ttk.Label(container, text=f"{COMPANY_NAME}\n{COMPANY_TAGLINE}", style="Header.TLabel", anchor="center")
        banner.pack(fill=tk.X)

        # Meta panel
        meta = ttk.LabelFrame(container, text="Invoice Details", padding=10)
        meta.pack(fill=tk.X, pady=(8,6))

        self.var_invoice_no = tk.StringVar()
        self.var_date = tk.StringVar()
        self.var_cust_name = tk.StringVar()
        self.var_cust_contact = tk.StringVar()
        self.var_cust_gstin = tk.StringVar()
        self.var_gst_rate = tk.StringVar(value="18")

        # Row 1
        ttk.Label(meta, text="Invoice No:").grid(row=0, column=0, sticky=tk.W)
        self.ent_invoice = ttk.Entry(meta, textvariable=self.var_invoice_no, width=28)
        self.ent_invoice.grid(row=0, column=1, padx=6, pady=4)

        ttk.Label(meta, text="Date (YYYY-MM-DD):").grid(row=0, column=2, sticky=tk.W)
        self.ent_date = ttk.Entry(meta, textvariable=self.var_date, width=18)
        self.ent_date.grid(row=0, column=3, padx=6, pady=4)

        ttk.Label(meta, text="GST %:").grid(row=0, column=4, sticky=tk.W)
        self.ent_gst = ttk.Entry(meta, textvariable=self.var_gst_rate, width=10)
        self.ent_gst.grid(row=0, column=5, padx=6, pady=4)

        # Row 2
        ttk.Label(meta, text="Customer Name:").grid(row=1, column=0, sticky=tk.W)
        self.ent_cname = ttk.Entry(meta, textvariable=self.var_cust_name, width=28)
        self.ent_cname.grid(row=1, column=1, padx=6, pady=4)

        ttk.Label(meta, text="Contact:").grid(row=1, column=2, sticky=tk.W)
        self.ent_ccontact = ttk.Entry(meta, textvariable=self.var_cust_contact, width=18)
        self.ent_ccontact.grid(row=1, column=3, padx=6, pady=4)

        ttk.Label(meta, text="GSTIN:").grid(row=1, column=4, sticky=tk.W)
        self.ent_cgstin = ttk.Entry(meta, textvariable=self.var_cust_gstin, width=18)
        self.ent_cgstin.grid(row=1, column=5, padx=6, pady=4)

        # Row 3 (Address full width)
        ttk.Label(meta, text="Address:").grid(row=2, column=0, sticky=tk.NW)
        self.txt_address = tk.Text(meta, height=3, width=85)
        self.txt_address.grid(row=2, column=1, columnspan=5, padx=6, pady=4, sticky="we")

        for i in range(6):
            meta.columnconfigure(i, weight=1)

        # Items panel
        items_box = ttk.LabelFrame(container, text="Items", padding=10)
        items_box.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(items_box, columns=("name","qty","rate","discount","amount"), show="headings")
        self.tree.heading("name", text="Item Description")
        self.tree.heading("qty", text="Qty")
        self.tree.heading("rate", text="Rate (₹)")
        self.tree.heading("discount", text="Discount (₹)")
        self.tree.heading("amount", text="Amount (₹)")
        self.tree.column("name", width=450)
        self.tree.column("qty", width=80, anchor=tk.E)
        self.tree.column("rate", width=110, anchor=tk.E)
        self.tree.column("discount", width=120, anchor=tk.E)
        self.tree.column("amount", width=120, anchor=tk.E)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scroll = ttk.Scrollbar(items_box, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Item entry row
        entry_row = ttk.Frame(container)
        entry_row.pack(fill=tk.X, pady=6)

        self.var_item = tk.StringVar()
        self.var_qty = tk.StringVar(value="1")
        self.var_rate = tk.StringVar(value="0")
        self.var_discount = tk.StringVar(value="0")

        ttk.Label(entry_row, text="Item:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(entry_row, textvariable=self.var_item, width=40).grid(row=0, column=1, padx=6)
        ttk.Label(entry_row, text="Qty:").grid(row=0, column=2)
        ttk.Entry(entry_row, textvariable=self.var_qty, width=8).grid(row=0, column=3, padx=6)
        ttk.Label(entry_row, text="Rate (₹):").grid(row=0, column=4)
        ttk.Entry(entry_row, textvariable=self.var_rate, width=12).grid(row=0, column=5, padx=6)
        ttk.Label(entry_row, text="Discount (₹):").grid(row=0, column=6)
        ttk.Entry(entry_row, textvariable=self.var_discount, width=12).grid(row=0, column=7, padx=6)
        ttk.Button(entry_row, text="Add Item", command=self.add_item).grid(row=0, column=8, padx=6)
        ttk.Button(entry_row, text="Remove Selected", command=self.remove_selected).grid(row=0, column=9, padx=6)
        ttk.Button(entry_row, text="Clear Items", command=self.clear_items).grid(row=0, column=10, padx=6)

        for i in range(11):
            entry_row.columnconfigure(i, weight=0)
        entry_row.columnconfigure(1, weight=1)

        # Totals panel
        totals = ttk.LabelFrame(container, text="Totals", padding=10)
        totals.pack(fill=tk.X)

        self.var_subtotal = tk.StringVar(value="0.00")
        self.var_gst_amt = tk.StringVar(value="0.00")
        self.var_total = tk.StringVar(value="0.00")
        self.notes_text = tk.Text(totals, height=3, width=60)

        ttk.Label(totals, text="Subtotal (₹):").grid(row=0, column=0, sticky=tk.E)
        ttk.Label(totals, textvariable=self.var_subtotal, width=12, anchor='e').grid(row=0, column=1, padx=6)
        ttk.Label(totals, text="GST Amount (₹):").grid(row=0, column=2, sticky=tk.E)
        ttk.Label(totals, textvariable=self.var_gst_amt, width=12, anchor='e').grid(row=0, column=3, padx=6)
        ttk.Label(totals, text="Grand Total (₹):", style="Header.TLabel").grid(row=0, column=4, sticky=tk.E)
        ttk.Label(totals, textvariable=self.var_total, width=14, anchor='e', style="Header.TLabel").grid(row=0, column=5, padx=6)

        ttk.Label(totals, text="Notes:").grid(row=1, column=0, sticky=tk.NE, pady=(8,0))
        self.notes_text.grid(row=1, column=1, columnspan=5, sticky='we', pady=(8,0))

        for i in range(6):
            totals.columnconfigure(i, weight=1)

        # Action buttons
        btns = ttk.Frame(container)
        btns.pack(fill=tk.X, pady=10)
        ttk.Button(btns, text="New Invoice", command=lambda: self._reset_form(new_invoice=True)).pack(side=tk.LEFT)
        ttk.Button(btns, text="Save Invoice", command=self.save_invoice).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="Save & Export PDF", command=self.save_and_export_pdf).pack(side=tk.LEFT)
        ttk.Button(btns, text="Export PDF Only", command=self.export_pdf_only).pack(side=tk.LEFT, padx=8)
        ttk.Button(btns, text="Open Output Folder", command=self.open_output_folder).pack(side=tk.RIGHT)

    # ---- Helpers ----
    def _reset_form(self, new_invoice: bool = False):
        if new_invoice:
            self.var_invoice_no.set(self.db.next_invoice_number())
            self.var_date.set(dt.date.today().isoformat())
            self.var_gst_rate.set("18")
        self.var_cust_name.set("")
        self.var_cust_contact.set("")
        self.var_cust_gstin.set("")
        self.txt_address.delete("1.0", tk.END)
        self.notes_text.delete("1.0", tk.END)
        self.clear_items()
        self.update_totals()

    def add_item(self):
        name = self.var_item.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Please enter an item description.")
            return
        try:
            qty = float(self.var_qty.get())
            rate = float(self.var_rate.get())
            discount = float(self.var_discount.get())
        except ValueError:
            messagebox.showerror("Invalid", "Qty, Rate and Discount must be numbers.")
            return
        if qty <= 0 or rate < 0 or discount < 0:
            messagebox.showerror("Invalid", "Enter valid positive values.")
            return
        amount = max(0.0, qty * rate - discount)
        self.tree.insert('', tk.END, values=(name, f"{qty:.2f}", f"{rate:.2f}", f"{discount:.2f}", f"{amount:.2f}"))
        # reset entry row except item name
        self.var_qty.set("1")
        self.var_rate.set("0")
        self.var_discount.set("0")
        self.var_item.set("")
        self.update_totals()

    def remove_selected(self):
        for sel in self.tree.selection():
            self.tree.delete(sel)
        self.update_totals()

    def clear_items(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.update_totals()

    def gather_items(self) -> List[Item]:
        items: List[Item] = []
        for row_id in self.tree.get_children():
            name, qty, rate, discount, amount = self.tree.item(row_id, 'values')
            items.append(Item(name=name, qty=float(qty), rate=float(rate), discount=float(discount)))
        return items

    def update_totals(self):
        items = self.gather_items()
        try:
            gst_rate = float(self.var_gst_rate.get() or 0)
        except ValueError:
            gst_rate = 0.0
        inv = Invoice(
            invoice_no=self.var_invoice_no.get(),
            date=self.var_date.get(),
            customer_name=self.var_cust_name.get(),
            customer_address=self.txt_address.get("1.0", tk.END).strip(),
            customer_contact=self.var_cust_contact.get(),
            customer_gstin=self.var_cust_gstin.get(),
            gst_rate=gst_rate,
            notes=self.notes_text.get("1.0", tk.END).strip(),
            items=items,
        )
        self.var_subtotal.set(f"{inv.subtotal:.2f}")
        self.var_gst_amt.set(f"{inv.gst_amount:.2f}")
        self.var_total.set(f"{inv.total:.2f}")

    def _validate_invoice(self) -> Optional[str]:
        if not self.var_invoice_no.get().strip():
            return "Invoice number is missing."
        # date format check
        try:
            dt.date.fromisoformat(self.var_date.get().strip())
        except Exception:
            return "Date must be in YYYY-MM-DD format."
        if not self.var_cust_name.get().strip():
            return "Customer name is required."
        if not self.gather_items():
            return "Add at least one item."
        try:
            float(self.var_gst_rate.get())
        except ValueError:
            return "GST % must be a number."
        return None

    def _build_invoice_obj(self) -> Invoice:
        self.update_totals()
        return Invoice(
            invoice_no=self.var_invoice_no.get().strip(),
            date=self.var_date.get().strip(),
            customer_name=self.var_cust_name.get().strip(),
            customer_address=self.txt_address.get("1.0", tk.END).strip(),
            customer_contact=self.var_cust_contact.get().strip(),
            customer_gstin=self.var_cust_gstin.get().strip(),
            gst_rate=float(self.var_gst_rate.get() or 0),
            notes=self.notes_text.get("1.0", tk.END).strip(),
            items=self.gather_items(),
        )

    # ---- Actions ----
    def save_invoice(self):
        err = self._validate_invoice()
        if err:
            messagebox.showerror("Cannot Save", err)
            return
        inv = self._build_invoice_obj()
        try:
            self.db.save_invoice(inv)
        except sqlite3.IntegrityError:
            resp = messagebox.askyesno("Duplicate Invoice No", "Invoice number exists. Overwrite?")
            if not resp:
                return
            self.db.save_invoice(inv)
        messagebox.showinfo("Saved", f"Invoice {inv.invoice_no} saved to database.")

    def export_pdf_only(self):
        err = self._validate_invoice()
        if err:
            messagebox.showerror("Cannot Export", err)
            return
        inv = self._build_invoice_obj()
        self._export_pdf(inv)

    def save_and_export_pdf(self):
        self.save_invoice()
        inv = self._build_invoice_obj()
        self._export_pdf(inv)

    def _export_pdf(self, inv: Invoice):
        # Ask user location (default invoices/)
        default_path = os.path.join(OUTPUT_DIR, f"{inv.invoice_no}.pdf")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=f"{inv.invoice_no}.pdf",
            initialdir=os.path.abspath(OUTPUT_DIR),
            filetypes=[("PDF Files", "*.pdf")],
            title="Save Invoice PDF"
        )
        if not file_path:
            return
        out = self.pdf.build(inv, file_path)
        messagebox.showinfo("Exported", f"PDF generated:\n{out}")

    def open_output_folder(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.abspath(OUTPUT_DIR)
        try:
            if os.name == 'nt':
                os.startfile(path)  # type: ignore[attr-defined]
            elif os.name == 'posix':
                import subprocess
                subprocess.Popen(['xdg-open', path])
            else:
                messagebox.showinfo("Folder", f"Saved at: {path}")
        except Exception:
            messagebox.showinfo("Folder", f"Saved at: {path}")


if __name__ == "__main__":
    app = InvoiceApp()
    # Recalculate totals when GST field changes focus
    def _on_gst_change(event):
        app.update_totals()
    app.ent_gst.bind("<FocusOut>", _on_gst_change)
    app.mainloop()
