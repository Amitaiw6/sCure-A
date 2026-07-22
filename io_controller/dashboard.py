#!/usr/bin/env python3
"""Simplified GPIO dashboard: stable layout and reliable quick-edit dialog.

This minimal version focuses on working read/write/mode controls and avoids
complex scrollable canvases so it behaves consistently across platforms.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading

from config import PINS, TCA6424A_ADDR, TCA6424A_ALT_ADDR, TCA6424A_MAP
from gpio_manager import (
    GpioManager, scan_i2c_bus, I2C_KNOWN_DEVICES, SMBUS_AVAILABLE,
    tca6424a_read_inputs, tca6424a_set_output,
    available_i2c_buses, probe_i2c_address,
    set_i2c_pins_alt3, I2C_ALT3_PINS,
)


class PinDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title('Raspberry Pi GPIO Dashboard (Simple)')
        self.manager = GpioManager()
        self.selected_pin = None

        # UI variables
        self.mode_var = tk.StringVar(value='IN')
        self.pull_var = tk.StringVar(value='down')
        self.write_value_var = tk.StringVar(value='HIGH')

        # Auto-refresh state
        self.live_var = tk.BooleanVar(value=True)
        self.poll_interval = 10000  # ms between status reads (10 seconds)
        self._poll_job = None
        self._refreshing = False
        self._closing = False
        self._expander_win = None
        self._expander_bus = 1
        self._expander_addr = TCA6424A_ADDR
        self._expander_value_labels = {}
        # Keep the I2C pins locked to their ALT3 (I2C) function.
        self.lock_i2c_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._populate_pin_table()
        self.apply_i2c_alt3(log=True)  # put I2C0/I2C1 pins into ALT3 at startup
        self._poll_pins()  # start the live update loop

    def _build_ui(self):
        # Main frames: left tree, right controls
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill='both', expand=True)

        left = ttk.Frame(main)
        left.pack(side='left', fill='both', expand=True)

        # Right column is scrollable, so the controls + 40-pin map + I2C panel
        # are all reachable even when the window is taller than the screen.
        right_outer = ttk.Frame(main)
        right_outer.pack(side='right', fill='y')
        right_canvas = tk.Canvas(right_outer, width=340, highlightthickness=0, borderwidth=0)
        right_scroll = ttk.Scrollbar(right_outer, orient='vertical', command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_scroll.pack(side='right', fill='y')
        right_canvas.pack(side='left', fill='both', expand=True)
        right = ttk.Frame(right_canvas)
        right_window = right_canvas.create_window((0, 0), window=right, anchor='nw')

        def _on_right_config(event):
            right_canvas.configure(scrollregion=right_canvas.bbox('all'))
            right_canvas.itemconfigure(right_window, width=right_canvas.winfo_width())
        right.bind('<Configure>', _on_right_config)

        # Mouse-wheel scrolling, scoped to the right column so it doesn't fight
        # with the table. Bound on enter, released on leave.
        def _wheel(event):
            delta = -1 if getattr(event, 'num', None) == 4 else 1 if getattr(event, 'num', None) == 5 else int(-event.delta / 120)
            right_canvas.yview_scroll(delta, 'units')

        def _bind_wheel(_):
            right_canvas.bind_all('<MouseWheel>', _wheel)
            right_canvas.bind_all('<Button-4>', _wheel)
            right_canvas.bind_all('<Button-5>', _wheel)

        def _unbind_wheel(_):
            right_canvas.unbind_all('<MouseWheel>')
            right_canvas.unbind_all('<Button-4>')
            right_canvas.unbind_all('<Button-5>')
        right_canvas.bind('<Enter>', _bind_wheel)
        right_canvas.bind('<Leave>', _unbind_wheel)

        # Treeview
        self.tree = ttk.Treeview(left, columns=('phys', 'bcm', 'name', 'type', 'value', 'mode'), show='headings')
        for col, lbl, w in [('phys', 'Pin', 50), ('bcm', 'BCM', 60), ('name', 'Name / Signal', 220), ('type', 'Type', 80), ('value', 'Value', 60), ('mode', 'Mode', 60)]:
            self.tree.heading(col, text=lbl)
            self.tree.column(col, width=w, anchor='center' if col in ('phys','bcm','value','mode') else 'w')
        self.tree.bind('<<TreeviewSelect>>', self._on_pin_select)
        self.tree.bind('<Double-1>', self._on_tree_double_click)
        # Row colors by value state
        self.tree.tag_configure('high', background='#c8e6c9')   # green = HIGH
        self.tree.tag_configure('low', background='#ffcdd2')    # red = LOW
        self.tree.tag_configure('err', background='#e0e0e0')    # gray = err/unknown
        self.tree.pack(fill='both', expand=True, side='left')

        # Controls (right)
        controls = ttk.LabelFrame(right, text='Selected Pin Controls', padding=6)
        controls.pack(fill='x', pady=(0,6))

        ttk.Checkbutton(controls, text='Auto refresh (10s)', variable=self.live_var).pack(anchor='w')
        ttk.Button(controls, text='Refresh now', command=self.refresh_pins).pack(fill='x', pady=(2,6))

        ttk.Label(controls, text='Selected Pin').pack(anchor='w')
        self.pin_label = ttk.Label(controls, text='(none)')
        self.pin_label.pack(anchor='w', pady=(0,6))

        ttk.Label(controls, text='BCM').pack(anchor='w')
        self.bcm_label = ttk.Label(controls, text='-')
        self.bcm_label.pack(anchor='w', pady=(0,6))

        ttk.Label(controls, text='Mode').pack(anchor='w')
        self.mode_display = ttk.Label(controls, text='-')
        self.mode_display.pack(anchor='w', pady=(0,6))

        b_read = ttk.Button(controls, text='Read', command=self.read_selected_pin)
        b_read.pack(fill='x', pady=(4,2))
        b_whigh = ttk.Button(controls, text='Write HIGH', command=lambda: self.write_selected_pin(1))
        b_whigh.pack(fill='x', pady=2)
        b_wlow = ttk.Button(controls, text='Write LOW', command=lambda: self.write_selected_pin(0))
        b_wlow.pack(fill='x', pady=2)

        ttk.Separator(controls).pack(fill='x', pady=6)
        b_min = ttk.Button(controls, text='Set Mode (IN)', command=lambda: self.set_selected_mode('IN'))
        b_min.pack(fill='x', pady=2)
        b_mout = ttk.Button(controls, text='Set Mode (OUT)', command=lambda: self.set_selected_mode('OUT'))
        b_mout.pack(fill='x', pady=2)

        ttk.Separator(controls).pack(fill='x', pady=6)
        b_qedit = ttk.Button(controls, text='Quick Edit', command=self._open_quick_edit_for_selection)
        b_qedit.pack(fill='x', pady=2)

        # GPIO controls that must be disabled for dedicated-function pins (I2C).
        self._gpio_buttons = [b_read, b_whigh, b_wlow, b_min, b_mout, b_qedit]
        # Note shown when a pin can't be used as plain GPIO.
        self.gpio_note = ttk.Label(controls, text='', foreground='#c62828', wraplength=300, justify='left')
        self.gpio_note.pack(anchor='w', pady=(4, 0))

        # 40-pin header map
        map_frame = ttk.LabelFrame(right, text='40-pin Header Map', padding=6)
        map_frame.pack(fill='x', pady=(0,6))
        self._build_header_map(map_frame)

        # I2C bus scan
        i2c_frame = ttk.LabelFrame(right, text='I2C Bus', padding=6)
        i2c_frame.pack(fill='x')
        ttk.Button(i2c_frame, text='Scan I2C', command=self._scan_i2c).pack(fill='x')
        self.i2c_text = tk.Text(i2c_frame, height=6, width=30, state='disabled')
        self.i2c_text.pack(fill='x', pady=(4,0))
        self.expander_btn = ttk.Button(
            i2c_frame, text='Open I/O Expander Map',
            command=lambda: self._show_expander_map(self._expander_bus),
        )
        self.expander_btn.pack(fill='x', pady=(4,0))
        ttk.Button(i2c_frame, text='I2C Diagnostics',
                   command=self._run_i2c_diagnostics).pack(fill='x', pady=(2,0))
        ttk.Button(i2c_frame, text='Force I2C pins -> ALT3',
                   command=lambda: self.apply_i2c_alt3(log=True)).pack(fill='x', pady=(2,0))
        ttk.Checkbutton(i2c_frame, text='Keep I2C pins in ALT3',
                        variable=self.lock_i2c_var).pack(anchor='w', pady=(2,0))

        # Log
        self.log_text = tk.Text(self.root, height=8, state='disabled')
        self.log_text.pack(fill='x')

    def _build_header_map(self, parent):
        # Visual 2-column map of the physical 40-pin header. Odd pins on the
        # left column, even pins on the right, matching the real board layout.
        type_colors = {
            'power': '#e53935',   # red
            'ground': '#424242',  # dark gray
            'gpio': '#43a047',    # green
        }
        self.map_buttons = {}
        for pin in sorted(PINS, key=lambda p: p['phys']):
            phys = pin['phys']
            row = (phys - 1) // 2
            col = (phys - 1) % 2
            notes = (pin.get('notes') or '')
            color = type_colors.get(pin['type'], '#43a047')
            if 'I2C' in notes:
                color = '#1e88e5'  # blue for I2C pins
            short = pin['name'].split(' /')[0]
            btn = tk.Button(
                parent, text=f'{phys}: {short}', bg=color, fg='white',
                relief='raised', bd=1, anchor='w', padx=2,
                font=('TkDefaultFont', 7),
                command=lambda p=phys: self._select_phys(p),
            )
            btn.grid(row=row, column=col, padx=1, pady=1, sticky='nsew')
            self.map_buttons[phys] = btn
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

    def _select_phys(self, phys):
        # Select a pin in the table from the header map; this fires the
        # <<TreeviewSelect>> binding which updates the controls panel.
        iid = str(phys)
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self.tree.focus(iid)

    def _run_async(self, work, done):
        # Run blocking `work()` in a daemon thread, then deliver the result to
        # `done(result, err)` back on the Tk main thread. Keeps the GUI from
        # freezing during GPIO reads / I2C scans.
        def runner():
            try:
                result, err = work(), None
            except Exception as e:  # noqa: BLE001 - surface any failure to the UI
                result, err = None, e
            if self._closing:
                return
            try:
                self.root.after(0, lambda: done(result, err))
            except RuntimeError:
                pass  # interpreter / Tk shutting down

        threading.Thread(target=runner, daemon=True).start()

    def _set_i2c_text(self, lines):
        self.i2c_text.configure(state='normal')
        self.i2c_text.delete('1.0', 'end')
        self.i2c_text.insert('end', lines)
        self.i2c_text.configure(state='disabled')

    def _scan_i2c(self, bus=1):
        # If the smbus2 library isn't installed we can never see anything, so
        # say so explicitly instead of a misleading "no devices found".
        if not SMBUS_AVAILABLE:
            self._set_i2c_text('smbus2 not installed.\nRun:  pip install smbus2\nand enable I2C (raspi-config).\n')
            self._log('I2C scan skipped: smbus2 not installed')
            return

        # Show progress immediately, then scan in the background.
        self._set_i2c_text(f'Bus {bus}: scanning...\n')

        def done(devices, err):
            if err is not None:
                self._set_i2c_text(f'Bus {bus}:\nScan error: {err}\n')
                self._log(f'I2C scan error: {err}')
                return
            lines = f'Bus {bus}:\n'
            if not devices:
                lines += 'No I2C devices found\n(check wiring / I2C enabled in raspi-config)\n'
            else:
                for addr in devices:
                    name = I2C_KNOWN_DEVICES.get(addr, 'Unknown device')
                    lines += f'0x{addr:02X}  {name}\n'
            self._set_i2c_text(lines)
            self._log(f'I2C scan (bus {bus}): {len(devices)} device(s) found')

            # If the TCA6424A I/O expander is on this bus, enable its map button
            # and pop the map open automatically (once).
            expander = next((a for a in (TCA6424A_ADDR, TCA6424A_ALT_ADDR) if a in devices), None)
            if expander is not None:
                self._expander_bus = bus
                self._expander_addr = expander
                self.expander_btn.config(state='normal')
                if self._expander_win is None or not self._expander_win.winfo_exists():
                    self._show_expander_map(bus, expander)
            else:
                self.expander_btn.config(state='disabled')

        self._run_async(lambda: scan_i2c_bus(bus), done)

    def apply_i2c_alt3(self, log=False):
        # Force GPIO0-3 into ALT3 (I2C) using `pinctrl`. Runs in the background
        # so a missing/slow pinctrl never blocks the UI.
        def work():
            return set_i2c_pins_alt3()

        def done(results, err):
            if err is not None:
                if log:
                    self._log(f'pinctrl error: {err}')
                return
            if log:
                summary = ', '.join(f'GPIO{p}={"a3" if ok else msg}' for p, ok, msg in results)
                self._log(f'I2C pins -> ALT3: {summary}')

        self._run_async(work, done)

    def _run_i2c_diagnostics(self):
        # Scan both buses and probe the TCA6424A addresses, reporting the exact
        # result of each step in a popup so the user can see why I2C fails.
        win = tk.Toplevel(self.root)
        win.title('I2C Diagnostics')
        win.geometry('560x420')
        win.transient(self.root)
        txt = tk.Text(win, wrap='word', state='disabled')
        txt.pack(fill='both', expand=True, padx=6, pady=6)

        def show(report):
            txt.configure(state='normal')
            txt.delete('1.0', 'end')
            txt.insert('end', report)
            txt.configure(state='disabled')

        show('Running diagnostics...\n')

        def work():
            lines = ['=== I2C Diagnostics ===\n']
            lines.append(f'smbus2 installed : {"yes" if SMBUS_AVAILABLE else "NO - run: pip install smbus2"}')
            if not SMBUS_AVAILABLE:
                return '\n'.join(lines) + '\n'
            buses = available_i2c_buses()
            lines.append(f'Kernel I2C buses : {buses if buses else "NONE - enable I2C in raspi-config / config.txt"}')
            # Always try the two common Pi buses even if /dev listing is odd.
            for b in sorted(set(buses) | {0, 1}):
                lines.append('')
                lines.append(f'--- Bus {b} (/dev/i2c-{b}) ---')
                try:
                    found = scan_i2c_bus(b)
                except Exception as e:
                    lines.append(f'  open failed: {e}')
                    continue
                if found:
                    lines.append('  devices: ' + ', '.join(
                        f'0x{a:02X} ({I2C_KNOWN_DEVICES.get(a, "?")})' for a in found))
                else:
                    lines.append('  devices: none')
                for addr in (TCA6424A_ADDR, TCA6424A_ALT_ADDR):
                    ok, msg = probe_i2c_address(addr, b)
                    mark = 'OK <== TCA6424A here!' if ok else msg
                    lines.append(f'  probe 0x{addr:02X}: {mark}')
            lines.append('')
            lines.append('Hints:')
            lines.append('- "bus not enabled" -> enable that bus (i2c-1: raspi-config; i2c-0: dtparam=i2c_vc=on).')
            lines.append('- chip found on a bus -> set TCA6424A bus in the expander window to that number.')
            lines.append('- nothing anywhere    -> check EXT_3V3 power, RESET high, SDA/SCL wiring & pull-ups.')
            return '\n'.join(lines) + '\n'

        def done(report, err):
            show(report if err is None else f'Diagnostics error: {err}\n')

        self._run_async(work, done)

    def _show_expander_map(self, bus=1, address=None):
        # Open (or focus) the TCA6424A I/O-expander window: one row per I/O,
        # showing the connected net, its live value, and ON/OFF controls.
        if address is None:
            address = self._expander_addr
        self._expander_bus = bus
        self._expander_addr = address

        if self._expander_win is not None and self._expander_win.winfo_exists():
            self._expander_win.lift()
            self._refresh_expander_values()
            return

        win = tk.Toplevel(self.root)
        self._expander_win = win
        win.title(f'TCA6424A I/O Expander (0x{address:02X}) - I2C{bus}')
        win.geometry('470x600')
        win.transient(self.root)

        header = ttk.Frame(win, padding=6)
        header.pack(fill='x')
        ttk.Label(header, text='TCA6424A', font=('TkDefaultFont', 10, 'bold')).pack(side='left')

        # Bus + address selectors so the user can hunt for the chip live
        # (e.g. the schematic "I2C1" net may be wired to the Pi's i2c-0).
        ttk.Label(header, text='Bus').pack(side='left', padx=(10, 2))
        self._exp_bus_var = tk.StringVar(value=str(bus))
        ttk.Combobox(header, textvariable=self._exp_bus_var, values=('0', '1'),
                     width=3, state='readonly').pack(side='left')
        ttk.Label(header, text='Addr 0x').pack(side='left', padx=(8, 0))
        self._exp_addr_var = tk.StringVar(value=f'{address:02X}')
        ttk.Combobox(header, textvariable=self._exp_addr_var, values=('22', '23'),
                     width=4, state='readonly').pack(side='left')

        def _apply_and_read():
            try:
                self._expander_bus = int(self._exp_bus_var.get())
                self._expander_addr = int(self._exp_addr_var.get(), 16)
            except ValueError:
                return
            win.title(f'TCA6424A I/O Expander (0x{self._expander_addr:02X}) - I2C{self._expander_bus}')
            self._refresh_expander_values()
        ttk.Button(header, text='Connect', command=_apply_and_read).pack(side='right')

        # Status line: shows exactly what the last chip read/write did.
        self.expander_status = ttk.Label(win, text='Reading chip...', anchor='w', foreground='#555')
        self.expander_status.pack(fill='x', padx=8, pady=(0, 4))

        cols = ttk.Frame(win, padding=(10, 0))
        cols.pack(fill='x')
        ttk.Label(cols, text='Pin / Net', width=26, anchor='w').pack(side='left')
        ttk.Label(cols, text='Val', width=4).pack(side='left', padx=4)
        ttk.Label(cols, text='Control').pack(side='left')

        # Scrollable list of the 24 expander I/O lines.
        body_outer = ttk.Frame(win)
        body_outer.pack(fill='both', expand=True)
        canvas = tk.Canvas(body_outer, highlightthickness=0)
        sb = ttk.Scrollbar(body_outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(canvas)
        bwin = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(bwin, width=e.width))

        self._expander_value_labels = {}
        for item in TCA6424A_MAP:
            row = ttk.Frame(body, padding=(6, 2))
            row.pack(fill='x')
            text = f"{item['pin']}  {item['net'] or '(unused)'}"
            ttk.Label(row, text=text, width=26, anchor='w').pack(side='left')
            val_lbl = tk.Label(row, text='-', width=4, relief='groove', bg='#e0e0e0')
            val_lbl.pack(side='left', padx=4)
            self._expander_value_labels[(item['port'], item['bit'])] = val_lbl
            ttk.Button(row, text='ON', width=4,
                       command=lambda it=item: self._set_expander_output(it, 1)).pack(side='left', padx=1)
            ttk.Button(row, text='OFF', width=4,
                       command=lambda it=item: self._set_expander_output(it, 0)).pack(side='left', padx=1)

        def _on_close():
            self._expander_win = None
            win.destroy()
        win.protocol('WM_DELETE_WINDOW', _on_close)
        win.lift()

        self._refresh_expander_values()

    def _refresh_expander_values(self):
        # Read the 3 input-port registers and color each row by its live value.
        if self._expander_win is None or not self._expander_win.winfo_exists():
            return
        addr, bus = self._expander_addr, self._expander_bus

        def _status(text, color):
            if self._expander_win and self._expander_win.winfo_exists():
                self.expander_status.config(text=text, foreground=color)

        if not SMBUS_AVAILABLE:
            for lbl in self._expander_value_labels.values():
                lbl.config(text='-', bg='#e0e0e0')
            _status('smbus2 not installed - run: pip install smbus2', '#c62828')
            return

        def done(ports, err):
            if not (self._expander_win and self._expander_win.winfo_exists()):
                return
            if err is not None or ports is None:
                for lbl in self._expander_value_labels.values():
                    lbl.config(text='-', bg='#e0e0e0')
                msg = str(err) if err is not None else 'no response from 0x%02X' % addr
                _status(f'Cannot read 0x{addr:02X} on I2C{bus}: {msg}', '#c62828')
                self._log(f'Expander read error: {msg}')
                return
            for (port, bit), lbl in self._expander_value_labels.items():
                v = (ports[port] >> bit) & 1
                lbl.config(text=str(v), bg='#c8e6c9' if v else '#ffcdd2')
            _status(f'Connected: read 0x{addr:02X} on I2C{bus} OK '
                    f'(P0=0x{ports[0]:02X} P1=0x{ports[1]:02X} P2=0x{ports[2]:02X})', '#2e7d32')

        _status(f'Reading 0x{addr:02X} on I2C{bus}...', '#555')
        self._run_async(lambda: tca6424a_read_inputs(addr, bus), done)

    def _set_expander_output(self, item, value):
        # Drive one expander output high/low (configures it as output first).
        addr, bus = self._expander_addr, self._expander_bus

        def done(ok, err):
            if err is not None:
                self._log(f"Expander write error ({item['pin']}): {err}")
                messagebox.showerror('I/O Expander', str(err))
                return
            if not ok:
                self._log('Expander write skipped: smbus2 not installed')
                return
            self._log(f"Set {item['pin']} {item['net'] or ''} = {value}")
            self._refresh_expander_values()

        self._run_async(
            lambda: tca6424a_set_output(addr, item['port'], item['bit'], value, bus),
            done,
        )

    def _is_i2c_pin(self, pin):
        # Returns the I2C bus number for an SDA/SCL pin, or None otherwise.
        notes = (pin.get('notes') or '') + ' ' + pin.get('name', '')
        if 'SDA' not in notes and 'SCL' not in notes:
            return None
        # GPIO0/GPIO1 are the ID-EEPROM bus (bus 0); GPIO2/GPIO3 are bus 1.
        return 0 if pin.get('bcm') in (0, 1) else 1

    def _populate_pin_table(self):
        for pin in sorted(PINS, key=lambda p: p['phys']):
            bcm = pin['bcm'] if pin['bcm'] is not None else '-'
            self.tree.insert('', 'end', iid=str(pin['phys']), values=(pin['phys'], bcm, pin['name'], pin['type'], '---', 'IN'))

    def _on_pin_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        phys = int(sel[0])
        pin = next((p for p in PINS if p['phys'] == phys), None)
        self.selected_pin = pin
        self.pin_label.config(text=pin['name'])
        self.bcm_label.config(text=str(pin['bcm'] or '-'))
        mode = self.manager.get_mode(pin['bcm']) if pin['bcm'] is not None else '-'
        self.mode_display.config(text=mode)

        # Decide whether this pin may be driven as plain GPIO. I2C (and other
        # non-GPIO) pins must not be reconfigured or it breaks the bus.
        bus = self._is_i2c_pin(pin)
        if bus is not None:
            self._set_gpio_controls(False, f'{pin["name"]} is an I2C bus pin - '
                                           'GPIO control is disabled to avoid disrupting I2C.')
        elif pin['bcm'] is None:
            self._set_gpio_controls(False, f'{pin["name"]} is a {pin["type"]} pin - not a GPIO.')
        else:
            self._set_gpio_controls(True, '')

        # If this is an I2C pin, scan its bus and list the connected devices.
        if bus is not None:
            self._log(f'I2C pin selected ({pin["name"]}) — scanning bus {bus}...')
            self._scan_i2c(bus)

    def _set_gpio_controls(self, enabled, note):
        # Enable/disable the Read/Write/Mode/Quick-Edit buttons as a group.
        state = 'normal' if enabled else 'disabled'
        for btn in self._gpio_buttons:
            btn.config(state=state)
        self.gpio_note.config(text=note)

    def _value_tag(self, val):
        # Pick the row color tag for a given pin value.
        if val == 1 or val == '1':
            return 'high'
        if val == 0 or val == '0':
            return 'low'
        return 'err'

    def refresh_pins(self):
        # Read every GPIO pin in a background thread, then update the table on
        # the main thread. Skips if a previous refresh is still running.
        if self._refreshing:
            return
        self._refreshing = True

        def work():
            data = []
            for pin in PINS:
                bcm = pin['bcm']
                if bcm is None:
                    continue
                # Never poke I2C bus pins as GPIO - it would disrupt I2C.
                if self._is_i2c_pin(pin) is not None:
                    data.append((pin['phys'], 'I2C', 'I2C'))
                    continue
                try:
                    val = self.manager.read_pin(bcm)
                except Exception:
                    val = 'err'
                data.append((pin['phys'], val, self.manager.get_mode(bcm)))
            return data

        def done(data, err):
            self._refreshing = False
            if err is not None:
                self._log(f'Refresh error: {err}')
                return
            for phys, val, mode in data:
                iid = str(phys)
                try:
                    self.tree.set(iid, 'value', val)
                    self.tree.set(iid, 'mode', mode)
                    self.tree.item(iid, tags=(self._value_tag(val),))
                except tk.TclError:
                    pass  # row gone / widget destroyed
            if self.selected_pin and self.selected_pin.get('bcm') is not None:
                self.mode_display.config(text=self.manager.get_mode(self.selected_pin['bcm']))
            self._log('Status refreshed')

        self._run_async(work, done)

    def _poll_pins(self):
        # Periodic status update; always reschedules itself so the loop can
        # never die on an error. Toggled by the "Auto refresh" checkbox.
        try:
            # Keep the I2C pins pinned to ALT3 in case anything reset them.
            if self.lock_i2c_var.get():
                self.apply_i2c_alt3(log=False)
            if self.live_var.get():
                self.refresh_pins()
        except Exception as e:  # noqa: BLE001 - keep the loop alive no matter what
            self._log(f'Poll error: {e}')
        finally:
            if not self._closing:
                self._poll_job = self.root.after(self.poll_interval, self._poll_pins)

    def _on_tree_double_click(self, event):
        # Double-clicking a row opens the quick-edit dialog for that pin.
        row = self.tree.identify_row(event.y)
        if not row:
            return
        phys = int(row)
        pin = next((p for p in PINS if p['phys'] == phys), None)
        if pin is None:
            return
        self.selected_pin = pin
        self.tree.selection_set(row)
        if self._block_if_not_gpio(pin, 'edit'):
            return
        self._open_quick_edit(pin)

    def read_selected_pin(self):
        if not self.selected_pin or self.selected_pin.get('bcm') is None:
            self._log('No GPIO selected')
            return
        try:
            val = self.manager.read_pin(self.selected_pin['bcm'])
            iid = str(self.selected_pin['phys'])
            self.tree.set(iid, 'value', val)
            self.tree.item(iid, tags=(self._value_tag(val),))
            self._log(f'Read GPIO{self.selected_pin["bcm"]} = {val}')
        except Exception as e:
            self._log(f'Read error: {e}')
            messagebox.showerror('Read Error', str(e))

    def _block_if_not_gpio(self, pin, action='control'):
        # Returns True (and warns) if the pin must not be used as plain GPIO.
        if pin is None or pin.get('bcm') is None:
            messagebox.showinfo('Not a GPIO', 'This pin is not a GPIO.')
            return True
        if self._is_i2c_pin(pin) is not None:
            messagebox.showwarning(
                'I2C pin',
                f'{pin["name"]} is an I2C bus pin.\n'
                f'GPIO {action} is disabled to avoid disrupting the I2C bus.')
            self._log(f'Blocked GPIO {action} on I2C pin {pin["name"]}')
            return True
        return False

    def write_selected_pin(self, value):
        if not self.selected_pin or self.selected_pin.get('bcm') is None:
            self._log('No GPIO selected')
            return
        if self._block_if_not_gpio(self.selected_pin, 'write'):
            return
        try:
            self.manager.write_pin(self.selected_pin['bcm'], value)
            iid = str(self.selected_pin['phys'])
            self.tree.set(iid, 'value', value)
            self.tree.item(iid, tags=(self._value_tag(value),))
            self._log(f'Wrote GPIO{self.selected_pin["bcm"]} = {value}')
        except Exception as e:
            self._log(f'Write error: {e}')
            messagebox.showerror('Write Error', str(e))

    def set_selected_mode(self, mode):
        if not self.selected_pin or self.selected_pin.get('bcm') is None:
            self._log('No GPIO selected')
            return
        if self._block_if_not_gpio(self.selected_pin, 'mode change'):
            return
        try:
            self.manager.set_mode(self.selected_pin['bcm'], mode.lower())
            self.mode_display.config(text=self.manager.get_mode(self.selected_pin['bcm']))
            self._log(f'Set GPIO{self.selected_pin["bcm"]} mode={mode}')
        except Exception as e:
            self._log(f'Mode error: {e}')
            messagebox.showerror('Mode Error', str(e))

    def _open_quick_edit_for_selection(self):
        if not self.selected_pin:
            messagebox.showinfo('Quick Edit', 'Select a pin first')
            return
        if self._block_if_not_gpio(self.selected_pin, 'edit'):
            return
        self._open_quick_edit(self.selected_pin)

    def _open_quick_edit(self, pin):
        top = tk.Toplevel(self.root)
        top.title(f'Edit Pin {pin["phys"]}')
        top.geometry('300x220')
        top.transient(self.root)

        ttk.Label(top, text=f'Pin: {pin["phys"]}').pack(anchor='w', padx=8, pady=6)
        ttk.Label(top, text=f'BCM: {pin["bcm"] or "-"}').pack(anchor='w', padx=8)

        frame = ttk.Frame(top)
        frame.pack(fill='x', padx=8, pady=8)
        ttk.Label(frame, text='Mode').grid(row=0, column=0, sticky='w')
        mode_var = tk.StringVar(value=self.manager.get_mode(pin['bcm']) if pin['bcm'] is not None else 'IN')
        ttk.Combobox(frame, textvariable=mode_var, values=('IN','OUT'), state='readonly', width=8).grid(row=0, column=1, sticky='e')

        def do_set_mode():
            try:
                self.manager.set_mode(pin['bcm'], mode_var.get().lower())
                self._log(f'Set GPIO{pin["bcm"]} mode={mode_var.get()}')
                top.destroy()
            except Exception as e:
                messagebox.showerror('Mode Error', str(e))

        ttk.Button(top, text='Set Mode', command=do_set_mode).pack(fill='x', padx=8, pady=(0,6))

        ttk.Label(top, text='Write value').pack(anchor='w', padx=8)
        write_var = tk.StringVar(value='HIGH')
        ttk.Combobox(top, textvariable=write_var, values=('HIGH','LOW'), state='readonly', width=8).pack(anchor='w', padx=8, pady=(0,6))

        def do_write():
            try:
                v = 1 if write_var.get() == 'HIGH' else 0
                self.manager.write_pin(pin['bcm'], v)
                self.tree.set(str(pin['phys']), 'value', v)
                self._log(f'Wrote GPIO{pin["bcm"]} = {v}')
                top.destroy()
            except Exception as e:
                messagebox.showerror('Write Error', str(e))

        ttk.Button(top, text='Write', command=do_write).pack(fill='x', padx=8, pady=(0,6))

        # Keep the dialog above the main window but NON-modal: a grab_set() here
        # made the whole app appear frozen while the dialog was open (and on the
        # Pi could raise "grab failed: window not viewable"). transient() is
        # enough to keep it on top without locking the rest of the UI.
        top.lift()

    def _log(self, msg):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', msg + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def on_close(self):
        self._closing = True
        if self._poll_job is not None:
            try:
                self.root.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        self.manager.cleanup()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = PinDashboard(root)
    root.protocol('WM_DELETE_WINDOW', app.on_close)
    root.mainloop()


if __name__ == '__main__':
    main()
