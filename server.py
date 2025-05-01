from gpiozero import Servo
import time
import json
import socket
import threading
from datetime import datetime
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle
from kivy.utils import get_color_from_hex


DATA_FILE = "taskData.json"


COLOR_LABELS = {
    "Easy": {"text_color": (0.5, 1, 0.5, 1), "button_color": (0.5, 1, 0.5, 1)},
    "Moderate": {"text_color": (1, 1, 0.3, 1), "button_color": (1, 1, 0.3, 1)},
    "Important": {"text_color": (1, 0.6, 0, 1), "button_color": (1, 0.6, 0, 1)},
    "Urgent": {"text_color": (1, 0.3, 0.3, 1), "button_color": (1, 0.3, 0.3, 1)},
    "Crucial": {"text_color": (0.7, 0.3, 1, 1), "button_color": (0.7, 0.3, 1, 1)},
}


def format_time(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"
    elif seconds >= 60:
        m = seconds // 60
        s = seconds % 60
        return f"{m}m {s}s"
    else:
        return f"{seconds}s"


class TaskWidget(BoxLayout):
    def __init__(self, task_data, app=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = 60
        self.task_data = task_data
        self.time_left = int(task_data["timer"])
        self.pending_approval = False
        self.app = app


        label = task_data.get("color_label", "Easy")
        colors = COLOR_LABELS.get(label, COLOR_LABELS["Easy"])


        self.label = Label(
            text=f"Task: {task_data['task']} | Time Left: {format_time(self.time_left)}",
            font_size='24sp',
            color=colors["text_color"]
        )
        self.add_widget(self.label)


        self.finish_btn = Button(
            text="Finish",
            size_hint_x=0.3,
            background_color=colors["button_color"],
            color=(1, 1, 1)
        )
        self.finish_btn.bind(on_press=self.finish_pressed)
        self.add_widget(self.finish_btn)


        if self.time_left > 0:
            Clock.schedule_interval(self.update_timer, 1)


    def update_timer(self, dt):
        if self.time_left > 0 and not self.pending_approval:
            self.time_left -= 1
            if self.time_left > 0:
                self.label.text = f"Task: {self.task_data['task']} | Time Left: {format_time(self.time_left)}"
            else:
                self.label.text = f"Task: {self.task_data['task']} | Time's Up!"
        return True


    def finish_pressed(self, instance):
        if self.app:
            self.pending_approval = True
            self.label.text = f"Task: {self.task_data['task']} | Pending Approval"
            self.finish_btn.disabled = True  # Disable after requesting approval

            # Determine whether this was a missed or on-time finish
            status = "missed" if self.time_left <= 0 else "finished"

            approval_request = {
                "action": "request_approval",
                "task": self.task_data["task"],
                "timer": self.task_data["timer"],
                "date": self.task_data["date"],
                "force_status": status
            }
            try:
                self.app.client_socket.send(json.dumps(approval_request).encode())
            except Exception as e:
                print("Failed to send approval request:", e)




class ServerApp(App):
    def build(self):
        self.servo = Servo(18, min_pulse_width=0.0005, max_pulse_width=0.0025)


        # Load saved Level and XP
        try:
            with open("taskData.json", "r") as file:
                data = json.load(file)
                self.level = data.get("level", 1)
                self.xp = data.get("xp", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            self.level = 1
            self.xp = 0


        self.completed_tasks = 0
        self.tasks_to_level = 5


        self.root = BoxLayout(orientation="vertical")
        with self.root.canvas.before:
            Color(*get_color_from_hex("#8365bd"))
            self.bg_rect = Rectangle(size=self.root.size, pos=self.root.pos)
            self.root.bind(size=self.update_bg, pos=self.update_bg)


        self.level_label = Label(
            text=f"Level {self.level}",
            font_size='36sp',
            size_hint_y=None,
            height=70,
            color=(1, 1, 1, 1)
        )
        self.root.add_widget(self.level_label)


        self.progress_bar = ProgressBar(max=self.xp_to_next_level(), value=self.xp, size_hint_y=None, height=30)
        self.root.add_widget(self.progress_bar)


        self.scroll_view = ScrollView(size_hint=(1, 1))
        self.task_container = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=20)
        self.task_container.bind(minimum_height=self.task_container.setter('height'))
        self.scroll_view.add_widget(self.task_container)
        self.root.add_widget(self.scroll_view)


        return self.root


    def dispense_reward(self):
        try:
            print("Dispensing reward!")
            self.servo.value = 1.0   # fully “release”
            time.sleep(1)
            self.servo.value = 0.0   # center/stop
            time.sleep(1)
        except Exception as e:
            print(f"Error while dispensing reward: {e}")
            
    def xp_to_next_level(self):
        base_xp = 100
        increase_rate = 0.10
        increments = (self.level - 1) // 10
        return int(base_xp * (1 + increase_rate * increments))


    def check_level_up(self):
        while self.xp >= self.xp_to_next_level():
            self.xp -= self.xp_to_next_level()
            self.level += 1
            print(f"LEVEL UP! Now Level {self.level}")


            if self.level % 1 == 0:
                self.dispense_reward()


        self.update_progress()
        self.save_progress()


    def check_level_down(self):
        while self.xp < 0 and self.level > 1:
            self.level -= 1
            self.xp += self.xp_to_next_level()
            print(f"LEVEL DOWN! Now Level {self.level}")


        if self.xp < 0:
            self.xp = 0


        self.update_progress()
        self.save_progress()


    def finish_task(self, task_data):
        self.remove_task(task_data)

        status = task_data.get("force_status", "finished").lower()

        if status == "missed":
            # Calculate penalty for missed task
            penalty_multiplier = 0.5 + 0.25 * (self.level // 10)
            penalty_xp = int(10 * penalty_multiplier)
            self.xp -= penalty_xp
            print(f"Missed task penalty: -{penalty_xp} XP")
            self.check_level_down()
        elif status == "finished":
            # Only award XP for completed tasks
            self.xp += 10
            self.check_level_up()

        self.update_progress()


        # Echo message back to client
        finish_message = {
            "action": "finish",
            "task": task_data["task"],
            "timer": task_data.get("timer"),
            "date": task_data["date"],
            "force_status": status
        }
        try:
            self.client_socket.send(json.dumps(finish_message).encode())
        except Exception as e:
            print("Error sending finish message:", e)

    def update_bg(self, *args):
        self.bg_rect.size = self.root.size
        self.bg_rect.pos = self.root.pos


    def on_start(self):
        self.selected_theme = "Default"
        load_pending_tasks(self)


    def add_task(self, task_data):
        new_task = TaskWidget(task_data, app=self)
        self.task_container.add_widget(new_task)
        self.save_progress()

    def edit_task(self, task_data):
        # remove by date, then re-add with the updated task_data
        self.remove_task(task_data)
        self.add_task(task_data)


    def remove_task(self, task_data):
        for widget in list(self.task_container.children):
            td = widget.task_data
            # match solely on the unique "date" field so renamed tasks still get removed
            if td.get("date") == task_data.get("date"):
                self.task_container.remove_widget(widget)
                break


    def approve_task(self, task_data):
        # Always trust the force_status that came in from the client
        status = task_data.get("force_status", "finished").lower()

        for widget in list(self.task_container.children):
            td = widget.task_data
            if td.get("task") == task_data["task"] and td.get("date") == task_data["date"]:
                # Remove the widget from UI
                self.remove_task(td)

                if status == "missed":
                    # Deduct XP for a missed task
                    penalty_multiplier = 0.5 + 0.25 * (self.level // 10)
                    penalty_xp = int(10 * penalty_multiplier)
                    self.xp -= penalty_xp
                    print(f"Missed task penalty: -{penalty_xp} XP")
                    self.check_level_down()
                else:
                    # Award XP for a successful completion
                    self.xp += 10
                    self.check_level_up()

                # Refresh progress bar and persist changes
                self.update_progress()
                self.save_progress()
                break



           
    def calculate_penalty(self):
        penalty_multiplier = 0.5 + 0.25 * (self.level // 10)
        penalty_points = penalty_multiplier
        return penalty_points


    def reset_progress(self):
        # Reset both level and XP in state
        self.level = 1
        self.xp = 0
        self.completed_tasks = 0
        # Update visuals and persist immediately
        self.update_progress()  # updates bar.max, bar.value, and level_label.text
        self.save_progress()    # writes new level & xp to taskData.json

        print("Server level and XP have been fully reset.")



    def reject_task(self, task_name):
        for widget in list(self.task_container.children):
            td = widget.task_data
            if td.get("task") == task_name:
                widget.pending_approval = False
                widget.finish_btn.disabled = False
                if widget.time_left > 0:
                    widget.label.text = f"Task: {widget.task_data['task']} | Time Left: {format_time(widget.time_left)}"
                else:
                    widget.label.text = f"Task: {widget.task_data['task']} | Time's Up!"
               
                # Popup
                content = Label(
                    text=f"Rejected:\n'{task_name}' has not been completed.",
                    halign="center",
                    valign="middle",
                    color=(1, 1, 1, 1)
                )
                content.bind(size=content.setter('text_size'))
                popup = Popup(
                    title="Task Rejected",
                    content=content,
                    size_hint=(None, None),
                    size=(400, 250)
                )
                popup.open()


                # XP Penalty for incorrect completion claim
                self.xp -= 5  # Flat deduction for rejected approval
                self.check_level_down()
                self.update_progress()
                break


    def save_progress(self):
        try:
            with open("taskData.json", "r") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}


        data["level"] = self.level
        data["xp"] = self.xp
       
        tasks = []
        for widget in self.task_container.children:
            task = widget.task_data.copy()
            task["pending"] = not widget.pending_approval
            task["date"] = task["date"]  # Ensure date remains
            tasks.append(task)


        data["tasks"] = tasks


        with open("taskData.json", "w") as file:
            json.dump(data, file, indent=4)


    def update_progress(self):
        self.progress_bar.max = self.xp_to_next_level()
        self.progress_bar.value = self.xp
        self.level_label.text = f"Level {self.level}"



# server.py
def load_pending_tasks(app):
    try:
        with open(DATA_FILE, "r") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        print("No previous task data found.")
        return

    now = datetime.now()

    for task in data.get("tasks", []):
        # only reload those still pending
        if not task.get("pending", False):
            continue

        # compute remaining time (may be zero)
        try:
            added = datetime.strptime(task["date"], "%Y-%m-%d %H:%M:%S")
            elapsed = (now - added).total_seconds()
            remaining = task["timer"] - int(elapsed)
        except Exception:
            remaining = task.get("timer", 0)

        task_copy = task.copy()
        task_copy["timer"] = max(remaining, 0)

        # schedule onto the UI
        Clock.schedule_once(lambda dt, t=task_copy: app.add_task(t))
        print(f"Loaded pending task: {task['task']} (remaining {task_copy['timer']}s)")


def listen_for_tasks(app, client_socket):
    while True:
        try:
            data = client_socket.recv(1024).decode()
            message = json.loads(data)
            action = message.get("action", "add")

            if action == "delete":
                task_name = message.get("task")
                task_date = message.get("date")
                Clock.schedule_once(lambda dt: app.remove_task({
                    "task": task_name,
                    "date": task_date
                }))
                Clock.schedule_once(lambda dt: app.save_progress())
                client_socket.send(f"Task '{task_name}' deleted.".encode())
            elif action == "edit":
                Clock.schedule_once(lambda dt, msg=message: app.edit_task(msg))
                client_socket.send(f"Task '{message.get('task')}' updated.".encode())
                pass
            elif action == "approve_task":
                Clock.schedule_once(lambda dt, msg=message: app.approve_task(msg))
                client_socket.send(f"Task '{message.get('task', 'unknown')}' approved.".encode())
            elif action == "finish":
                Clock.schedule_once(lambda dt, msg=message: app.finish_task(msg))
                client_socket.send("Task finish acknowledged".encode())
            elif action == "reject_task":
                task = message.get("task")
                Clock.schedule_once(lambda dt: app.reject_task(task))
                client_socket.send(f"Task '{task}' rejected.".encode())
            elif action == "reset_level":
                Clock.schedule_once(lambda dt: app.reset_progress())
                client_socket.send("Server level reset acknowledged.".encode())


            else:
                Clock.schedule_once(lambda dt, msg=message: app.add_task(msg))
                client_socket.send("Task added.".encode())            


        except Exception as e:
            print("Error in task listener:", e)
            break


if __name__ == "__main__":
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', 9999))
    server.listen(5)
    print("Server is listening...")


    client_socket, addr = server.accept()
    print(f"Connected to {addr}")


    app = ServerApp()
    app.client_socket = client_socket
    app.selected_theme = "Default"
    threading.Thread(target=listen_for_tasks, args=(app, client_socket), daemon=True).start()
    app.run()
    GPIO.cleanup()

    client_socket.close()
    server.close()