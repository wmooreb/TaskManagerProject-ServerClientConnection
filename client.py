import json
import socket
import threading
from datetime import datetime
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.core.window import Window
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('172.20.10.10', 9999))

DATA_FILE = "taskData.json"

COLOR_LABELS = {
    "Easy": {"color": (0.5, 1, 0.5, 1)},
    "Moderate": {"color": (1, 1, 0.3, 1)},
    "Important": {"color": (1, 0.6, 0, 1)},
    "Urgent": {"color": (1, 0.3, 0.3, 1)},
    "Crucial": {"color": (0.7, 0.3, 1, 1)},
}

TIME_MULTIPLIERS = {
    "Seconds": 1,
    "Minutes": 60,
    "Hours": 3600,
}

class MyGridLayout(GridLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cols = 2
        self.size_hint = (1, 1)

        self.editing = False
        self.editing_task = None

        self.left_panel = GridLayout(cols=1, size_hint_x=0.6)

        # Top grid for Task + Timer + Pending
        self.top_grid = GridLayout(cols=2, row_force_default=True, row_default_height=80)

        # Add Task
        self.top_grid.add_widget(Label(
            text="Add task:", 
            color=(1, 1, 1, 1),
            font_size='24sp',
            size_hint_y=None,
            height=80,
            halign="right",
            valign="middle"
        ))
        self.tasksAdd = TextInput(
            multiline=False,
            size_hint=(1, 1),
            height=80,
            pos_hint={"center_y": 0.5},
            padding_y=(5, 5)
        )
        self.top_grid.add_widget(self.tasksAdd)

        # Set Timer
        self.top_grid.add_widget(Label(
            text="Set Timer:", 
            color=(1, 1, 1, 1),
            font_size='24sp',
            size_hint_y=None,
            height=80,
            halign="right",
            valign="middle"
        ))
        timer_box = BoxLayout(orientation="horizontal", spacing=10, size_hint_y=None, height=80)
        self.timerInput = TextInput(
            multiline=False,
            size_hint=(0.5, 1),
            height=80,
            pos_hint={"center_y": 0.5},
            padding_y=(5, 5)
        )
        self.time_unit_spinner = Spinner(
            text="Minutes",
            values=list(TIME_MULTIPLIERS.keys()),
            size_hint=(0.5, 1),
            height=80,
            pos_hint={"center_y": 0.5}
        )
        timer_box.add_widget(self.timerInput)
        timer_box.add_widget(self.time_unit_spinner)
        self.top_grid.add_widget(timer_box)

        # Tasks Pending
        self.top_grid.add_widget(Label(
            text="Tasks pending:", 
            color=(1, 1, 1, 1),
            font_size='24sp',
            size_hint_y=None,
            height=50,
            halign="right",
            valign="middle"
        ))
        self.tasksDone = Label(
            text="0",
            font_size='24sp',
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=50,
            valign="middle"
        )
        self.top_grid.add_widget(self.tasksDone)

        self.left_panel.add_widget(self.top_grid)

        # Color Picker
        self.left_panel.add_widget(Label(
            text="Task Color:", 
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=50,
            halign="right",
            valign="middle"
        ))
        self.color_spinner = Spinner(
            text="Easy",
            values=list(COLOR_LABELS.keys()),
            size_hint_y=None,
            height=50,
            background_color=COLOR_LABELS["Easy"]["color"],
            color=(0, 0, 0, 1)
        )
        self.color_spinner.bind(text=self.on_color_selected)
        self.left_panel.add_widget(self.color_spinner)

        # Submit Button
        self.button_container = BoxLayout(orientation="horizontal", size_hint_y=None, height=100)
        self.submit = Button(text="Submit", font_size=32, background_color=(0, 1, 0, 1), color=(1, 1, 1))
        self.submit.bind(on_press=self.press)
        self.button_container.add_widget(self.submit)
        self.left_panel.add_widget(self.button_container)

        self.server_status = Label(text="Server Messages:", font_size='20sp', color=(1, 1, 1))
        self.error_label = Label(text="", font_size='20sp', color=(1, 0, 0, 1))
        self.left_panel.add_widget(self.server_status)
        self.left_panel.add_widget(self.error_label)

        self.reset_button_container = BoxLayout(orientation="horizontal", size_hint_y=None, height=100)
        self.reset_button = Button(
            text="Reset Server Level",
            font_size=24,
            background_color=(1, 0.2, 0.2, 1),
            color=(1, 1, 1),
            size_hint=(1, None),
            height=60
        )
        self.reset_button.bind(on_press=self.reset_server_level)
        self.reset_button_container.add_widget(self.reset_button)
        self.left_panel.add_widget(self.reset_button_container)

        self.add_widget(self.left_panel)

        # Right Panel
        self.right_panel = BoxLayout(orientation="vertical", size_hint_x=0.4)

        # Top Half - Task History
        self.history_container = BoxLayout(orientation="vertical", size_hint=(1, 0.5))
        self.history_label = Label(text="Task History", font_size='24sp', color=(1, 1, 1), size_hint_y=None, height=50)
        self.history_scroll = ScrollView(size_hint=(1, 1))
        self.history_content = GridLayout(cols=1, spacing=10, padding=10, size_hint_y=None)
        self.history_content.bind(minimum_height=self.history_content.setter('height'))
        self.history_scroll.add_widget(self.history_content)
        self.history_container.add_widget(self.history_label)
        self.history_container.add_widget(self.history_scroll)
        self.right_panel.add_widget(self.history_container)

        # Bottom Half - Pending Approvals
        self.approval_container = BoxLayout(orientation="vertical", size_hint=(1, 0.5))
        self.approval_label = Label(text="Pending Approvals", font_size='24sp', color=(1, 1, 1), size_hint_y=None, height=50)
        self.approval_scroll = ScrollView(size_hint=(1, 1))
        self.approval_content = GridLayout(cols=1, spacing=10, padding=10, size_hint_y=None)
        self.approval_content.bind(minimum_height=self.approval_content.setter('height'))
        self.approval_scroll.add_widget(self.approval_content)
        self.approval_container.add_widget(self.approval_label)
        self.approval_container.add_widget(self.approval_scroll)
        self.right_panel.add_widget(self.approval_container)


        self.add_widget(self.right_panel)


        self.load_tasks()
        Clock.schedule_interval(self.periodic_update, 1)
        threading.Thread(target=self.receive_messages, daemon=True).start()
    def on_color_selected(self, spinner, text):
        color = COLOR_LABELS.get(text, {}).get("color", (0.8, 0.8, 0.8, 1))
        spinner.background_color = color
       
    def reset_server_level(self, instance):
        try:
            reset_message = {"action": "reset_level"}
            client.send(json.dumps(reset_message).encode())
            self.update_server_status("Requested server level reset.")
        except Exception as e:
            self.update_server_status(f"Failed to reset level: {e}")


    def delete_local_only(self, task):
        try:
            with open(DATA_FILE, "r") as file:
                data = json.load(file)
        except:
            data = {"tasks": []}


        # Only delete locally — do NOT notify the server
        data["tasks"] = [t for t in data["tasks"] if not (t["task"] == task["task"] and t["date"] == task["date"])]


        with open(DATA_FILE, "w") as file:
            json.dump(data, file, indent=4)


   
    def press(self, instance):
        self.error_label.text = ""
        added_task = self.tasksAdd.text.strip()
        timer_str = self.timerInput.text.strip()
        color_label = self.color_spinner.text
        time_unit = self.time_unit_spinner.text


        if not added_task or not timer_str:
            self.error_label.text = "Please enter task name and timer."
            return
        try:
            raw_time = int(timer_str)
            if raw_time < 0:
                self.error_label.text = "Timer must be positive."
                return
            task_timer = raw_time * TIME_MULTIPLIERS[time_unit]
        except ValueError:
            self.error_label.text = "Timer must be numeric."
            return


        task_data = {
            "action": "add",
            "task": added_task,
            "timer": task_timer,
            "date": self.get_current_time_server_format(),
            "pending": True,
            "color_label": color_label,
            "sent_time": self.get_current_display_time()
        }


        client.send(json.dumps(task_data).encode())
        self.save_task(task_data)
        self.load_tasks()
        self.tasksAdd.text = ""
        self.timerInput.text = ""
        self.update_server_status("Task submitted.")


    def save_task(self, task_data):
        try:
            with open(DATA_FILE, "r") as file:
                data = json.load(file)
        except:
            data = {"tasks": []}
        data["tasks"].append(task_data)
        with open(DATA_FILE, "w") as file:
            json.dump(data, file, indent=4)


    def load_tasks(self):
        try:
            with open(DATA_FILE, "r") as file:
                data = json.load(file)
        except:
            return
        self.update_pending_count(data)
        self.update_task_history()


    def update_task_history(self):
        self.history_content.clear_widgets()
        try:
            with open(DATA_FILE, "r") as file:
                data = json.load(file)
        except:
            return


        for task in reversed(data["tasks"]):
            now = datetime.now()
            status = "Pending"


            try:
                added_time = datetime.strptime(task["date"], "%Y-%m-%d %H:%M:%S")
                elapsed = (now - added_time).total_seconds()


                if "status_override" in task:
                    status = task["status_override"]
                elif not task.get("pending", True):
                    status = "Finished"
                elif elapsed > task["timer"]:
                    status = "Missed"
            except:
                status = "Unknown"


            # Build timestamp receipt
            sent_time = task.get("sent_time", "")
            completed_time = task.get("completed_time", "")
            if completed_time:
                receipt = f"{sent_time} - {completed_time}"
            else:
                receipt = sent_time


            # Task appearance
            color = COLOR_LABELS.get(task.get("color_label", "Easy"), {}).get("color", (1, 1, 1, 1))
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=80, spacing=10, padding=10)


            label = Label(
                text=f"{task['task']} ({status})\n{receipt}",
                size_hint_x=0.6,
                color=color,
                font_size='18sp'
            )
            edit_btn = Button(text="Edit", size_hint_x=0.2, background_color=(0, 0.5, 1, 1), color=(1, 1, 1))
            del_btn = Button(text="X", size_hint_x=0.2, background_color=(1, 0, 0, 1), color=(1, 1, 1))


            edit_btn.bind(on_press=lambda b, t=task: self.enter_edit_mode(t))
            del_btn.bind(on_press=lambda b, t=task: self.delete_task(t))


            row.add_widget(label)
            row.add_widget(edit_btn)
            row.add_widget(del_btn)
            self.history_content.add_widget(row)




    def get_current_display_time(self):
        return datetime.now().strftime("%m/%d/%Y %H:%M")


    def get_current_time_server_format(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")




    def delete_task(self, task):
        try:
            with open(DATA_FILE, "r") as file:
                data = json.load(file)
        except:
            data = {"tasks": []}
        data["tasks"] = [t for t in data["tasks"] if t != task]
        with open(DATA_FILE, "w") as file:
            json.dump(data, file, indent=4)
        self.load_tasks()
        client.send(json.dumps({
            "action": "delete",
            "task": task["task"],
            "timer": task["timer"],
            "date": task["date"]
        }).encode())


    def receive_messages(self):
        while True:
            msg = client.recv(1024).decode()
            if not msg: break
            try:
                message = json.loads(msg)
                action = message.get("action", "add")
                # Treat server-side finish the same as a pending-approval request
                if action in ("request_approval", "finish"):
                    Clock.schedule_once(lambda dt, m=message: self.add_pending_approval(m))
                else:
                    Clock.schedule_once(lambda dt, m=msg: self.update_server_status(m))
            except:
                Clock.schedule_once(lambda dt, m=msg: self.update_server_status(m))



    def add_pending_approval(self, task_data):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=80, spacing=10)
        label = Label(text=f"{task_data['task']} (Pending)", size_hint_x=0.6, color=(1, 1, 1, 1), font_size='20sp')
        row.add_widget(label)

        status = task_data.get("force_status", "Pending").capitalize()
        if status.lower() == "missed":
            btn = Button(
                text="Accept (Missed)",
                size_hint_x=0.4,
                background_color=(1,1,0.2,1),
                color=(0,0,0,1),
                font_size='20sp'
            )
            btn.bind(on_press=lambda b: self.approve_task(task_data, row))
            row.add_widget(btn)
        else:
            approve_btn = Button(text="Approve", size_hint_x=0.2)
            reject_btn  = Button(text="Reject", size_hint_x=0.2)
            approve_btn.bind(on_press=lambda b: self.approve_task(task_data, row))
            reject_btn.bind(on_press=lambda b: self.reject_task(task_data, row))
            row.add_widget(approve_btn)
            row.add_widget(reject_btn)
        self.approval_content.add_widget(row)

    def approve_task(self, task_data, widget_row):
        try:
            self.approval_content.remove_widget(widget_row)
        except:
            pass

        # Determine approval status
        approval_status = task_data.get("force_status", "finished").lower()

        # 1) Update local JSON to mark task as finished or missed
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        except:
            data = {"tasks": []}

        for task in data.get("tasks", []):
            if task["task"] == task_data["task"] and task["date"] == task_data["date"]:
                task["pending"] = False
                task["status_override"] = approval_status.capitalize()
                task["completed_time"] = self.get_current_display_time()
                break

        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)

        # 2) Send approval back to server
        approval = {
            "action": "approve_task",
            "task": task_data["task"],
            "date": task_data["date"],
            "force_status": approval_status
        }
        try:
            client.send(json.dumps(approval).encode())
            self.update_server_status(f"Approved: {task_data['task']} ({approval_status})")
            # Reload tasks so history and pending count update immediately
            self.load_tasks()
        except Exception as e:
            self.update_server_status(f"Failed to approve task: {e}")


    def reject_task(self, task_data, widget_row):
        try:
            rejection = {"action": "reject_task", "task": task_data["task"]}
            client.send(json.dumps(rejection).encode())
            self.approval_content.remove_widget(widget_row)  # Remove it immediately after rejection
        except:
            self.update_server_status("Failed to reject task.")


    def enter_edit_mode(self, task):
        self.editing = True
        self.editing_task = task
        self.tasksAdd.text = task["task"]


        # Determine appropriate time unit
        timer_seconds = task["timer"]
        if timer_seconds % 3600 == 0:
            self.timerInput.text = str(timer_seconds // 3600)
            self.time_unit_spinner.text = "Hours"
        elif timer_seconds % 60 == 0:
            self.timerInput.text = str(timer_seconds // 60)
            self.time_unit_spinner.text = "Minutes"
        else:
            self.timerInput.text = str(timer_seconds)
            self.time_unit_spinner.text = "Seconds"


        self.color_spinner.text = task.get("color_label", "Easy")
        self.color_spinner.background_color = COLOR_LABELS[self.color_spinner.text]["color"]


        self.button_container.clear_widgets()
        confirm = Button(text="Confirm", font_size=32, background_color=(0, 1, 0, 1), color=(1, 1, 1))
        cancel = Button(text="Cancel", font_size=32, background_color=(1, 0, 0, 1), color=(1, 1, 1))
        confirm.bind(on_press=self.confirm_edit)
        cancel.bind(on_press=self.cancel_edit)
        self.button_container.add_widget(confirm)
        self.button_container.add_widget(cancel)




    def cancel_edit(self, instance):
        self.editing = False
        self.editing_task = None
        self.tasksAdd.text = ""
        self.timerInput.text = ""
        self.color_spinner.text = "Easy"
        self.color_spinner.background_color = COLOR_LABELS["Easy"]["color"]
        self.restore_submit_button()


    def confirm_edit(self, instance):
        task = self.editing_task
        updated_task = {
            "action": "edit",
            "task": self.tasksAdd.text.strip(),
            "timer": int(self.timerInput.text.strip()) * TIME_MULTIPLIERS[self.time_unit_spinner.text],
            "date": task["date"],
            "pending": True,
            "color_label": self.color_spinner.text,
            "sent_time": task.get("sent_time", self.get_current_display_time())  # preserve sent_time
        }
        if "completed_time" in task:
            updated_task["completed_time"] = task["completed_time"]  # preserve completed_time if it exists


        self.delete_local_only(task)
        self.save_task(updated_task)
        client.send(json.dumps(updated_task).encode())
        self.update_server_status("Task editing acknowledged.")
        self.editing = False
        self.editing_task = None
        self.tasksAdd.text = ""
        self.timerInput.text = ""
        self.restore_submit_button()
        self.load_tasks()




    def restore_submit_button(self):
        self.button_container.clear_widgets()
        self.button_container.add_widget(self.submit)


    def update_server_status(self, msg):
        self.server_status.text = "Server: " + msg


    def update_pending_count(self, *args):
        try:
            with open(DATA_FILE, "r") as file:
                data = json.load(file)
        except:
            data = {"tasks": []}

        # Count only truly pending tasks (no override → Pending)
        count = sum(
            1
            for task in data.get("tasks", [])
            if task.get("pending", True)
            and task.get("status_override", "").lower() not in ("finished", "missed")
        )
        self.tasksDone.text = str(count)



    def periodic_update(self, dt):
        self.load_tasks()
        self.update_pending_count()


    def get_current_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MyApp(App):
    def build(self):
        return MyGridLayout()


if __name__ == '__main__':
    MyApp().run()





