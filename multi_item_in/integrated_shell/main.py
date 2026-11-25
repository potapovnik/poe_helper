import json, sys
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTextEdit, QSpinBox, QGroupBox, QMessageBox)

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'config.json'
HISTORY_PATH = ROOT / 'history.json'
UI_AUTO_REFRESH = True  # Toggle periodic clipboard preview refresh during development
DEFAULT_CONFIG = {
    'delay_ms': 100,
    'grid_step_x': 65,
    'grid_step_y': 65,
    'offset_x': 0,
    'offset_y': 0,
    'refresh_interval_ms': 500,
    'window_width': 1120,
    'window_height': 760,
}

def load_config():
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        cfg = {**DEFAULT_CONFIG, **raw}
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')

def load_history():
    try:
        items = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
        return items if isinstance(items, list) else []
    except Exception:
        return []

def save_history(items):
    HISTORY_PATH.write_text(json.dumps(items[-200:], indent=2, ensure_ascii=False), encoding='utf-8')

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.history = load_history()
        self.setWindowTitle('Project Desktop — Control Panel')
        self.resize(self.cfg['window_width'], self.cfg['window_height'])
        self.setStyleSheet('''
            QWidget { background:#11151c; color:#e5e9f0; font-family:Segoe UI; font-size:10pt; }
            QGroupBox { border:1px solid #2b3442; border-radius:10px; margin-top:12px; padding:10px; font-weight:600; }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 4px; color:#9fb5d1; }
            QPushButton { background:#263447; border:1px solid #364a63; border-radius:8px; padding:9px 12px; }
            QPushButton:hover { background:#31445d; }
            QTextEdit { background:#0b0f14; border:1px solid #273241; border-radius:8px; padding:8px; }
            QSpinBox { background:#0b0f14; border:1px solid #273241; border-radius:6px; padding:5px; }
            QLabel#muted { color:#8d9bae; }
        ''')
        root = QWidget(); layout = QVBoxLayout(root); layout.setSpacing(12)
        header = QHBoxLayout()
        titlecol = QVBoxLayout()
        title = QLabel('PROJECT DESKTOP'); title.setStyleSheet('font-size:20pt;font-weight:700;letter-spacing:1px;')
        subtitle = QLabel('Embedded desktop UI • local configuration • clipboard history'); subtitle.setObjectName('muted')
        titlecol.addWidget(title); titlecol.addWidget(subtitle)
        header.addLayout(titlecol); header.addStretch()
        self.status = QLabel('● UI ready'); self.status.setStyleSheet('color:#7fc9a3;font-weight:600;')
        header.addWidget(self.status)
        layout.addLayout(header)

        body = QGridLayout(); body.setSpacing(12)
        settings = QGroupBox('Settings'); sg = QGridLayout(settings)
        self.spins = {}
        fields = [('delay_ms','Delay (ms)'),('grid_step_x','Grid step X'),('grid_step_y','Grid step Y'),('offset_x','Offset X'),('offset_y','Offset Y'),('refresh_interval_ms','UI refresh (ms)')]
        for idx,(key,label) in enumerate(fields):
            spin=QSpinBox(); spin.setRange(-10000,10000); spin.setValue(int(self.cfg[key])); self.spins[key]=spin
            sg.addWidget(QLabel(label), idx, 0); sg.addWidget(spin, idx, 1)
        buttons = QHBoxLayout()
        savebtn=QPushButton('Save settings'); savebtn.clicked.connect(self.save_settings)
        resetbtn=QPushButton('Reset defaults'); resetbtn.clicked.connect(self.reset_settings)
        buttons.addWidget(savebtn); buttons.addWidget(resetbtn)
        sg.addLayout(buttons, len(fields), 0, 1, 2)
        body.addWidget(settings,0,0)

        clipboard_box=QGroupBox('Clipboard preview (manual)'); cb=QVBoxLayout(clipboard_box)
        self.clipboard_text=QTextEdit(); self.clipboard_text.setPlaceholderText('Paste or type text here. Use the button to insert the current clipboard contents.'); cb.addWidget(self.clipboard_text)
        cbbuttons=QHBoxLayout(); paste=QPushButton('Paste from clipboard'); paste.clicked.connect(self.paste_clipboard)
        add=QPushButton('Add to history'); add.clicked.connect(self.add_history)
        clear=QPushButton('Clear preview'); clear.clicked.connect(self.clipboard_text.clear)
        cbbuttons.addWidget(paste); cbbuttons.addWidget(add); cbbuttons.addWidget(clear); cb.addLayout(cbbuttons)
        body.addWidget(clipboard_box,0,1)

        history_box=QGroupBox('Recent history'); hg=QVBoxLayout(history_box)
        self.history_view=QTextEdit(); self.history_view.setReadOnly(True); hg.addWidget(self.history_view)
        hbuttons=QHBoxLayout(); clearhist=QPushButton('Clear history'); clearhist.clicked.connect(self.clear_history)
        hbuttons.addWidget(clearhist); hg.addLayout(hbuttons)
        body.addWidget(history_box,1,0,1,2)
        body.setColumnStretch(0,1); body.setColumnStretch(1,2); body.setRowStretch(1,2)
        layout.addLayout(body)
        footer=QLabel('This shell is standalone: it does not control or launch the project’s gameplay automation.'); footer.setObjectName('muted')
        layout.addWidget(footer)
        self.setCentralWidget(root)
        self.render_history()

    def save_settings(self):
        for key, spin in self.spins.items(): self.cfg[key]=spin.value()
        self.cfg['window_width']=self.width(); self.cfg['window_height']=self.height()
        save_config(self.cfg); self.status.setText('● Settings saved'); self.log_event('Settings saved')

    def reset_settings(self):
        self.cfg=DEFAULT_CONFIG.copy()
        for key, spin in self.spins.items(): spin.setValue(int(self.cfg[key]))
        save_config(self.cfg); self.status.setText('● Defaults restored'); self.log_event('Settings reset to defaults')

    def paste_clipboard(self):
        text=QApplication.clipboard().text()
        if text: self.clipboard_text.setPlainText(text)
        else: self.status.setText('● Clipboard is empty')

    def add_history(self):
        text=self.clipboard_text.toPlainText().strip()
        if not text: return
        self.history.append({'time':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'text':text})
        save_history(self.history); self.render_history(); self.status.setText('● Added to history')

    def render_history(self):
        entries=[]
        for item in reversed(self.history[-100:]):
            entries.append(f"[{item.get('time','')}]\n{item.get('text','')}\n{'─'*45}")
        self.history_view.setPlainText('\n'.join(entries))

    def clear_history(self):
        self.history=[]; save_history(self.history); self.render_history()

    def log_event(self, msg):
        self.history.append({'time':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'text':f'[UI] {msg}'})
        save_history(self.history); self.render_history()

    def closeEvent(self, event):
        self.cfg['window_width']=self.width(); self.cfg['window_height']=self.height(); save_config(self.cfg)
        event.accept()

if __name__=='__main__':
    app=QApplication(sys.argv)
    win=MainWindow(); win.show()
    sys.exit(app.exec())
