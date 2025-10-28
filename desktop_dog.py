#!/usr/bin/env python3
import sys, json
from pathlib import Path
from datetime import date
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QPixmap, QCursor, QAction, QImage, QBitmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QMainWindow,
    QListWidget, QListWidgetItem, QLineEdit, QPushButton, QSpinBox, QFrame,
    QMenu, QSystemTrayIcon, QGridLayout
)

# -------------------- App config --------------------
APP_DIR = Path.home() / ".desktop_dog"
APP_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = APP_DIR / "data_v2.json"

MODES = ["Coding", "PTE", "Job Apps", "Work out"]
MODE_ICONS = {
    "Coding": "dog_coding.png",   # optional single-frame fallback
    "PTE": "dog_pte.png",
    "Job Apps": "dog_jobs.png",
    "Work out": "dog_workout.png",
}

# Per-mode animation speeds (ms per frame)
MODE_ANIM_MS = {
    "Coding": 200,
    "PTE": 600,
    "Job Apps": 700,
    "Offer": 700,  # if you use "Offer"
}
DEFAULT_ANIM_MS = 400

SIZES = {"Small": 220, "Medium": 300, "Large": 380}
DEFAULT_SIZE_KEY = "Small"
SMOOTH = Qt.SmoothTransformation

# -------------------- data I/O --------------------
def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "todos": [],
        "focus_log": {m: {"by_day": {}, "lifetime": 0} for m in MODES},
        "ui": {"mode": "Coding", "minutes": 25, "size_key": DEFAULT_SIZE_KEY}
    }

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# -------------------- Pet window --------------------
class DogPet(QWidget):
    """
    Coverable normal window (not forced on top). It stays alive across app switches.
    Hover raises it gently without stealing focus. Left-drag to move. Right-click menu.
    """
    def __init__(self, get_mode, set_mode, get_size_key, set_size_key, toggle_panel):
        super().__init__()
        self.get_mode = get_mode
        self.set_mode = set_mode
        self.get_size_key = get_size_key
        self.set_size_key = set_size_key
        self.toggle_panel = toggle_panel

        self._drag_pos: QPoint | None = None
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(DEFAULT_ANIM_MS)
        self._anim_timer.timeout.connect(self._advance_anim_frame)
        self._anim_frames: list[QImage] = []
        self._anim_index = 0

        # Normal window (coverable), frameless, transparent, no focus
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Window |                     # normal window: not hidden on app switch
            Qt.WindowDoesNotAcceptFocus     # never steals keyboard focus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.label = QLabel(self); self.label.setAlignment(Qt.AlignCenter)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.addWidget(self.label)

        self.update_appearance()
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu)

    # ----- helpers -----
    def _target_height(self) -> int:
        return SIZES.get(self.get_size_key(), SIZES[DEFAULT_SIZE_KEY])

    def _set_alpha_mask(self, img: QImage):
        try:
            mask = img.createAlphaMask()
            self.setMask(QBitmap.fromImage(mask))
        except Exception:
            pass

    def _apply_frame(self, img: QImage):
        pix = QPixmap.fromImage(img)
        self.label.setPixmap(pix)
        self.resize(pix.size())
        self._set_alpha_mask(img)

    def _load_three_frames(self, stem: Path) -> list[QImage]:
        paths = [Path(f"{stem}_{i}.png") for i in (0,1,2)]
        if not all(p.exists() for p in paths):
            return []
        th = self._target_height()
        frames = []
        for p in paths:
            img = QImage(str(p))
            if img.isNull(): return []
            if img.height() != th:
                img = img.scaledToHeight(th, SMOOTH)
            frames.append(img)
        return frames

    def _sync_anim_speed(self):
        self._anim_timer.setInterval(MODE_ANIM_MS.get(self.get_mode(), DEFAULT_ANIM_MS))

    # ----- appearance -----
    def update_appearance(self):
        mode = self.get_mode()
        self._sync_anim_speed()
        base = MODE_ICONS.get(mode, "")
        self._anim_timer.stop()
        self._anim_frames.clear()
        self._anim_index = 0

        # Prefer 3-frame PNG animation if available
        if base:
            frames = self._load_three_frames(Path(base).with_suffix(''))
            if frames:
                self._anim_frames = frames
                self._apply_frame(frames[0])
                self._anim_timer.start()
                return

        # Fallback single PNG
        if base and Path(base).exists():
            img = QImage(base)
            if not img.isNull():
                img = img.scaledToHeight(self._target_height(), SMOOTH)
                self._apply_frame(img)
                return

        # Emoji fallback: clear mask to avoid invisibility
        self.label.setText("🐶")
        self.label.setStyleSheet("font-size: 84px;")
        self.clearMask()

    def _advance_anim_frame(self):
        if not self._anim_frames: return
        seq = self._anim_frames + self._anim_frames[-2:0:-1]  # ping-pong
        self._anim_index = (self._anim_index + 1) % len(seq)
        self._apply_frame(seq[self._anim_index])

    # ----- interactions -----
    def enterEvent(self, e):
        # Hover-to-front: coverable, but easy to bring forward as needed
        self.raise_()
        return super().enterEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self._drag_pos:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e):
        self.toggle_panel()

    def wheelEvent(self, e):
        # Scroll to switch modes quickly
        delta = e.angleDelta().y()
        cur = self.get_mode()
        idx = MODES.index(cur)
        idx = (idx + 1) % len(MODES) if delta < 0 else (idx - 1) % len(MODES)
        self.set_mode(MODES[idx])
        self.update_appearance()

    def _open_menu(self, pos):
        menu = QMenu(self)

        # Mode submenu
        sm = QMenu("切换模式 / Mode", self)
        for m in MODES:
            act = QAction(m, self, checkable=True, checked=(m == self.get_mode()))
            act.triggered.connect(lambda checked, mm=m: (self.set_mode(mm), self.update_appearance()))
            sm.addAction(act)
        menu.addMenu(sm)

        # Size submenu
        sz = QMenu("大小 / Size", self)
        for key in SIZES.keys():
            act = QAction(key, self, checkable=True, checked=(key == self.get_size_key()))
            act.triggered.connect(lambda checked, k=key: (self.set_size_key(k), self.update_appearance()))
            sz.addAction(act)
        menu.addMenu(sz)

        menu.addAction("显示/隐藏控制面板", self.toggle_panel)
        menu.addAction("退出", QApplication.instance().quit)
        menu.exec(QCursor.pos())

# -------------------- Control panel (To-Do + Timer + Stats) --------------------
class ControlPanel(QMainWindow):
    def __init__(self, data_ref, on_change_mode, get_mode, get_size_key, set_size_key, save_cb, on_timer_end, sync_pet):
        super().__init__()
        self.data = data_ref
        self.on_change_mode = on_change_mode
        self.get_mode = get_mode
        self.get_size_key = get_size_key
        self.set_size_key = set_size_key
        self.save_cb = save_cb
        self.on_timer_end = on_timer_end
        self.sync_pet = sync_pet

        self.setWindowTitle("Desktop Dog 控制面板")
        self.setMinimumSize(560, 440)

        root = QWidget(); self.setCentralWidget(root)
        g = QGridLayout(root); g.setContentsMargins(12,12,12,12); g.setHorizontalSpacing(16); g.setVerticalSpacing(10)

        # ===== To-Do =====
        self.todo_input = QLineEdit(placeholderText="Add a task… 输入后回车添加")
        self.todo_list = QListWidget()
        self.todo_input.returnPressed.connect(self._add_todo)
        for it in self.data["todos"]:
            self._add_item(it["text"], it["done"])
        btn_del = QPushButton("删除选中  Delete"); btn_del.clicked.connect(self._delete_selected)
        btn_clear = QPushButton("清除已完成  Clear Done"); btn_clear.clicked.connect(self._clear_done)

        todo_box = QVBoxLayout()
        todo_box.addWidget(self.todo_input)
        todo_box.addWidget(self.todo_list)
        row = QHBoxLayout(); row.addWidget(btn_del); row.addWidget(btn_clear); todo_box.addLayout(row)

        # ===== Mode & Timer =====
        self.mode_btns = {}
        btn_row = QHBoxLayout()
        for m in MODES:
            b = QPushButton(m); b.setCheckable(True)
            b.clicked.connect(lambda checked, mm=m: self._switch_mode(mm))
            self.mode_btns[m] = b; btn_row.addWidget(b)
        self._refresh_mode_buttons()

        self.spin_minutes = QSpinBox(); self.spin_minutes.setRange(5, 180); self.spin_minutes.setValue(self.data["ui"].get("minutes", 25))
        self.btn_start = QPushButton("开始专注  Start")
        self.btn_stop  = QPushButton("停止  Stop"); self.btn_stop.setEnabled(False)
        self.lbl_time  = QLabel("00:00"); self.lbl_time.setStyleSheet("font-size: 28px; font-weight: 600;")
        self.lbl_today = QLabel(); self.lbl_total = QLabel(); self._refresh_stats()

        self.btn_start.clicked.connect(self._start_timer)
        self.btn_stop.clicked.connect(self._stop_timer)

        right = QVBoxLayout()
        right.addLayout(btn_row)
        r1 = QHBoxLayout(); r1.addWidget(QLabel("专注时长(分钟) Minutes:")); r1.addWidget(self.spin_minutes); right.addLayout(r1)
        right.addWidget(self.lbl_time)
        r2 = QHBoxLayout(); r2.addWidget(self.btn_start); r2.addWidget(self.btn_stop); right.addLayout(r2)
        right.addSpacing(8); right.addWidget(self.lbl_today); right.addWidget(self.lbl_total); right.addStretch(1)

        g.addWidget(self._grp("To-Do 待办", todo_box), 0, 0, 2, 1)
        g.addWidget(self._grp("Mode & Timer 模式与计时", right), 0, 1, 2, 1)

        # signals
        self.todo_list.itemChanged.connect(self._on_item_changed)

        # timer
        self.timer = QTimer(); self.timer.setInterval(1000); self.timer.timeout.connect(self._tick)
        self.remaining = 0; self._focusing = False

    def _grp(self, title, inner_layout):
        f = QFrame(); v = QVBoxLayout(f); v.setContentsMargins(10,8,10,10)
        t = QLabel(title); t.setStyleSheet("font-weight: 600;"); v.addWidget(t)
        box = QWidget(); box.setLayout(inner_layout); v.addWidget(box)
        return f

    # ----- To-Do -----
    def _add_item(self, text, done=False):
        it = QListWidgetItem(text)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it.setCheckState(Qt.Checked if done else Qt.Unchecked)
        self.todo_list.addItem(it)

    def _add_todo(self):
        t = self.todo_input.text().strip()
        if not t: return
        self._add_item(t, False); self.todo_input.clear(); self._dump_todos(); self._save()

    def _delete_selected(self):
        for it in self.todo_list.selectedItems():
            self.todo_list.takeItem(self.todo_list.row(it))
        self._dump_todos(); self._save()

    def _clear_done(self):
        i=0
        while i< self.todo_list.count():
            it = self.todo_list.item(i)
            if it.checkState()==Qt.Checked: self.todo_list.takeItem(i)
            else: i+=1
        self._dump_todos(); self._save()

    def _on_item_changed(self, item):
        self._dump_todos(); self._save()

    def _dump_todos(self):
        arr=[]
        for i in range(self.todo_list.count()):
            it = self.todo_list.item(i)
            arr.append({"text": it.text(), "done": it.checkState()==Qt.Checked})
        self.data["todos"]=arr

    # ----- Mode & Timer -----
    def _switch_mode(self, m):
        self.on_change_mode(m)
        self._refresh_mode_buttons()
        self._refresh_stats()
        self.sync_pet()

    def _refresh_mode_buttons(self):
        cur = self.get_mode()
        for m,b in self.mode_btns.items():
            b.setChecked(m==cur)
            b.setStyleSheet("font-weight:700;" if m==cur else "")

    def _start_timer(self):
        if self._focusing: return
        mins = self.spin_minutes.value()
        self.data["ui"]["minutes"] = mins
        self.remaining = mins*60
        self._focusing=True; self.btn_start.setEnabled(False); self.btn_stop.setEnabled(True)
        self.timer.start(); self._update_time_label(); self._save()

    def _stop_timer(self):
        if not self._focusing: return
        self.timer.stop()
        elapsed = self.data["ui"]["minutes"]*60 - self.remaining
        if elapsed<0: elapsed=0
        self._focusing=False; self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)
        self._accumulate(elapsed)
        self._update_time_label(); self._save()

    def _tick(self):
        self.remaining -= 1
        if self.remaining<=0:
            self.timer.stop(); self._focusing=False; self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)
            self._accumulate(self.data["ui"]["minutes"]*60)
            self._update_time_label(); self._save()
        else:
            self._update_time_label()

    def _update_time_label(self):
        s=max(self.remaining,0); self.lbl_time.setText(f"{s//60:02d}:{s%60:02d}")

    def _accumulate(self, seconds):
        mode = self.get_mode()
        d = date.today().isoformat()
        node = self.data["focus_log"].setdefault(mode, {"by_day":{}, "lifetime":0})
        node["by_day"][d] = node["by_day"].get(d,0)+int(seconds)
        node["lifetime"] = node.get("lifetime",0)+int(seconds)
        self._refresh_stats()

    def _refresh_stats(self):
        mode = self.get_mode()
        node = self.data["focus_log"].get(mode, {"by_day":{}, "lifetime":0})
        today = node["by_day"].get(date.today().isoformat(), 0)
        self.lbl_today.setText(f"{mode} 今日 Today：{today//60} min")
        self.lbl_total.setText(f"{mode} 累计 Total：{node['lifetime']//60} min")

    def _save(self):
        save_data(self.data)

# -------------------- App --------------------
class App(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationDisplayName("Desktop Dog")
        self.setQuitOnLastWindowClosed(False)

        self.data = load_data()
        self._mode = self.data["ui"].get("mode", "Coding")
        self._size_key = self.data["ui"].get("size_key", DEFAULT_SIZE_KEY)

        def get_mode(): return self._mode
        def set_mode(m): self._mode = m; self.data["ui"]["mode"] = m; save_data(self.data)
        def get_size_key(): return self._size_key
        def set_size_key(k): self._size_key = k; self.data["ui"]["size_key"] = k; save_data(self.data)

        self.panel = ControlPanel(
            data_ref=self.data,
            on_change_mode=set_mode,
            get_mode=get_mode,
            get_size_key=get_size_key,
            set_size_key=set_size_key,
            save_cb=lambda: save_data(self.data),
            on_timer_end=lambda: None,
            sync_pet=lambda: self.pet.update_appearance()
        )
        self.pet = DogPet(
            get_mode=get_mode, set_mode=set_mode,
            get_size_key=get_size_key, set_size_key=set_size_key,
            toggle_panel=self.toggle_panel
        )

        # System tray with recovery action
        self.tray = QSystemTrayIcon(self)
        icon_path = Path("dog_coding_0.png")
        self.tray.setIcon(QIcon(str(icon_path)) if icon_path.exists() else QIcon())
        self.tray.setVisible(True)

        tray_menu = QMenu()
        tray_menu.addAction(QAction("Show Panel / 显示面板", self, triggered=self.toggle_panel))

        def find_my_dog():
            self.data["ui"]["size_key"] = "Small"; save_data(self.data)
            self.pet.update_appearance()
            scr = self.primaryScreen().geometry()
            self.pet.move(scr.width()-self.pet.width()-40, scr.height()-self.pet.height()-80)
            self.pet.show(); self.pet.raise_()
        tray_menu.addAction(QAction("Find my dog / 找回小狗", self, triggered=find_my_dog))
        tray_menu.addAction(QAction("Quit / 退出", self, triggered=QApplication.instance().quit))
        self.tray.setContextMenu(tray_menu)

        # Initial placement
        screen = self.primaryScreen().geometry()
        self.pet.move(screen.width()-self.pet.width()-40, screen.height()-self.pet.height()-80)
        self.pet.show(); self.panel.hide()
        QTimer.singleShot(200, self.pet.raise_)  # gentle bring-forward once

    def toggle_panel(self):
        if self.panel.isVisible(): self.panel.hide()
        else: self.panel.showNormal(); self.panel.raise_()

if __name__ == "__main__":
    app = App(sys.argv)
    sys.exit(app.exec())
