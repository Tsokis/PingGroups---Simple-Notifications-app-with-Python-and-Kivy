import json, time, threading, random, string
from datetime import datetime
from functools import partial

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock, mainthread
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout

import requests
from plyer import notification

KV = """
<JoinScreen>:
    orientation: "vertical"
    padding: "20dp"
    spacing: "12dp"
    Label:
        text: "PingGroups"
        font_size: "28sp"
        bold: True
    TextInput:
        id: nickname
        hint_text: "Nickname"
        multiline: False
    BoxLayout:
        size_hint_y: None
        height: "40dp"
        spacing: "8dp"
        TextInput:
            id: groupcode
            hint_text: "Group Code (e.g., team42)"
            multiline: False
            text: root.prefilled_group or ""
        Button:
            text: "Request Code"
            size_hint_x: None
            width: "140dp"
            on_release: root.request_code()
    Button:
        text: "Join Group"
        size_hint_y: None
        height: "48dp"
        on_release: root.join(nickname.text.strip(), groupcode.text.strip())
    Label:
        text: root.status
        color: (1,0,0,1)
        font_size: "12sp"

<ChatScreen>:
    orientation: "vertical"
    padding: "16dp"
    spacing: "8dp"

    BoxLayout:
        size_hint_y: None
        height: "32dp"
        Label:
            text: "Group: [b]{}[/b] | Me: [b]{}[/b]".format(root.group_code, root.nickname)
            markup: True

    RecycleView:
        id: rv
        viewclass: "Label"
        bar_width: dp(6)
        RecycleBoxLayout:
            default_size: None, dp(40)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            orientation: "vertical"

    # typing indicator
    Label:
        id: typing_lbl
        size_hint_y: None
        height: "22dp"
        text: root.typing_text
        color: (.6,.6,.6,1)
        font_size: "12sp"

    # message input row
    BoxLayout:
        size_hint_y: None
        height: "48dp"
        spacing: "8dp"
        TextInput:
            id: msg_input
            hint_text: "Type a message…"
            multiline: False
            on_text: root.on_typing(self.text)
            on_text_validate: root.send_message(self.text)
        Button:
            text: "Send"
            on_release: root.send_message(msg_input.text)

    # optional quick actions
    BoxLayout:
        size_hint_y: None
        height: "44dp"
        spacing: "8dp"
        Button:
            text: "Send Alert"
            on_release: root.send_alert()
        Button:
            text: "Refresh"
            on_release: root.refresh_now()
"""

FIREBASE_URL = "Your firebase database cloud connection"
POLL_SECONDS = 4
TYPING_IDLE_SECONDS = 2.0

def fb_group_path(group_code):
    safe = group_code.replace("/", "_")
    return f"{FIREBASE_URL}/groups/{safe}.json"

def fb_typing_user_path(group_code, nickname):
    safe_g = group_code.replace("/", "_")
    safe_n = nickname.replace("/", "_")
    return f"{FIREBASE_URL}/typing/{safe_g}/{safe_n}.json"

def fb_typing_group_path(group_code):
    safe_g = group_code.replace("/", "_")
    return f"{FIREBASE_URL}/typing/{safe_g}.json"

class JoinScreen(BoxLayout):
    status = StringProperty("")
    prefilled_group = StringProperty("")

    def join(self, nickname, groupcode):
        if not nickname or not groupcode:
            self.status = "Please fill both fields."
            return
        app = App.get_running_app()
        app.nickname = nickname
        app.group_code = groupcode
        app.switch_to_chat()

    def request_code(self):
        """Generate a short code, create empty list in Firebase, and fill the field."""
        code = "grp-" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
        try:
            url = fb_group_path(code)
            r = requests.get(url, timeout=6)
            if r.status_code == 200 and r.json() in (None, {}):
                requests.put(url, data=json.dumps([]), timeout=6)
            self.ids.groupcode.text = code
            self.status = f"Created code: {code}"
        except Exception as e:
            self.status = f"Failed to create code. Try again."
            print("request_code error:", e)

class ChatScreen(BoxLayout):
    nickname = StringProperty("")
    group_code = StringProperty("")
    items = ListProperty([])
    typing_text = StringProperty("")
    _last_seen_ids = set()
    _polling = BooleanProperty(False)
    _typing_timer = None
    _i_am_typing = False

    def on_kv_post(self, base_widget):
        self.refresh_now()
        if not self._polling:
            self._polling = True
            threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        while self._polling:
            try:
                self._fetch_updates()
                self._fetch_typing()
            except Exception:
                pass
            time.sleep(POLL_SECONDS)

    def refresh_now(self):
        self._fetch_updates(force=True)
        self._fetch_typing()

    def send_message(self, text):
        text = (text or "").strip()
        if not text:
            return
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        payload = {
            "sender": self.nickname,
            "timestamp": now,
            "type": "message",
            "message": text
        }
        try:
            url = fb_group_path(self.group_code)
            r = requests.get(url, timeout=6)
            data = r.json() if r.ok and r.text else []
            if not isinstance(data, list):
                data = []
            data.append(payload)
            requests.put(url, data=json.dumps(data), timeout=6)
            try:
                self.ids.msg_input.text = ""
            except Exception:
                pass
            self._set_typing(False)
            self.refresh_now()
        except Exception as e:
            print("send_message error", e)

    def send_alert(self):
        self.send_message(f"ALERT from {self.nickname}")

    def on_typing(self, current_text):
        current_text = (current_text or "")
        self._set_typing(bool(current_text.strip()))
        if self._typing_timer:
            self._typing_timer.cancel()
        self._typing_timer = Clock.schedule_once(lambda dt: self._set_typing(False), TYPING_IDLE_SECONDS)

    def _set_typing(self, value: bool):
        if self._i_am_typing == value:
            return
        self._i_am_typing = value
        try:
            url = fb_typing_user_path(self.group_code, self.nickname)
            requests.put(url, data=json.dumps(bool(value)), timeout=4)
        except Exception as e:
            print("typing update error", e)

    def _fetch_typing(self):
        try:
            url = fb_typing_group_path(self.group_code)
            r = requests.get(url, timeout=6)
            data = r.json() or {}
            names = [n for (n, v) in (data or {}).items() if v and n != self.nickname]
            if not names:
                txt = ""
            elif len(names) == 1:
                txt = f"{names[0]} is typing…"
            else:
                txt = f"{', '.join(names[:3])}{'…' if len(names) > 3 else ''} are typing…"
            self._update_typing(txt)
        except Exception as e:
            pass

    @mainthread
    def _update_typing(self, txt):
        self.typing_text = txt

   
    def _fetch_updates(self, force=False):
        url = fb_group_path(self.group_code)
        r = requests.get(url, timeout=6)
        if not r.ok:
            return
        data = r.json() or []
        if not isinstance(data, list):
            data = []
        labeled = []
        new_ids = set()
        for idx, item in enumerate(data):
            msg = item.get("message", "")
            sender = item.get("sender", "unknown")
            ts = item.get("timestamp", "")
            line = f"[{ts}] {sender}: {msg}"
            labeled.append(line) 
            new_ids.add((ts, sender, msg))
        if self._last_seen_ids and (new_ids - self._last_seen_ids):
            self._notify(len(new_ids - self._last_seen_ids))
        self._last_seen_ids = new_ids
        self._update_list(labeled)

    @mainthread
    def _update_list(self, labeled):
        rv = self.ids.get("rv")
        rv.data = [{"text": s} for s in labeled] 
        Clock.schedule_once(lambda dt: self._auto_scroll_bottom(), 0)

    def _auto_scroll_bottom(self):
        rv = self.ids.get("rv")
        try:
            rv.scroll_y = 0
        except Exception:
            pass

    def _notify(self, count):
        try:
            title = "New message" if count == 1 else f"{count} new messages"
            notification.notify(title=title, message=f"Group {self.group_code}", timeout=3)
        except Exception as e:
            print("notify error", e)

class PingGroupsApp(App):
    nickname = StringProperty("")
    group_code = StringProperty("")
    join_widget = None
    chat_widget = None

    def build(self):
        Builder.load_string(KV)
        self.join_widget = JoinScreen()
        return self.join_widget

    def on_stop(self):
        if getattr(self, "chat_widget", None):
            try:
                self.chat_widget._set_typing(False)
            except Exception:
                pass

    def switch_to_chat(self):
        self.chat_widget = ChatScreen(nickname=self.nickname, group_code=self.group_code)
        self.root.clear_widgets()
        self.root.add_widget(self.chat_widget)

if __name__ == "__main__":
    PingGroupsApp().run()