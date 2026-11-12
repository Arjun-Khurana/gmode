import json
import svgwrite
import meep as mp
import numpy as np
import tkinter as tk
from tkinter import ttk
from index import calc_modes
from functools import partial
from PIL import Image, ImageTk
from matplotlib import pyplot as plt
from tkinter import filedialog, simpledialog, Toplevel

PX_PER_UM = 100

class WaveguideDrawer:
    def __init__(self, root):
        self.root = root
        self.root.title("Waveguide Mode Solver")
        self.root.geometry("300x300")
        self.root.resizable(True, True)  # Allow window resizing
        
        self.canvas = tk.Canvas(root, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.rectangles = {}  # Store rectangle data
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        self.current_text = None
        
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-2>", self.select_rectangle)
        
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)

        save_button = tk.Button(btn_frame, text="Calculate ", command=self.serialize)
        save_button.pack(side=tk.LEFT, padx=5)
        
        manual_button = tk.Button(btn_frame, text="Add Rectangle", command=self.add_rectangle_manually)
        manual_button.pack(side=tk.LEFT, padx=5)
        self.draw_grid()
    
    def get_color(self, id):
        max_idx = max(d['index'] for d in self.rectangles.values())
        color = int(100*(1 - (self.rectangles[id]['index'] / max_idx)))
        return color

    def remap_indices(self):
        for r in self.rectangles.keys():
            color = self.get_color(r)
            self.canvas.itemconfig(r, fill=f"gray{color}")
            if color < 50:
                self.canvas.itemconfig(self.rectangles[r]['text_id'], fill=f"white")
            else:
                self.canvas.itemconfig(self.rectangles[r]['text_id'], fill=f"black")

    def select_rectangle(self, event):
        for id,coord in [(id,r['coords']) for (id,r) in sorted(self.rectangles.items(), key=lambda i: i[0], reverse=True)]:
            x1, y1, x2, y2 = coord
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.current_rect = id
                self.current_text = self.rectangles[id]['text_id']
                self.show_edit_dialog(rect=self.rectangles[id])
                return

    def draw_grid(self):
        self.canvas.delete("grid")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        for x in range(0, width, 100):
            self.canvas.create_line(x, 0, x, height, fill="lightgray", tags="grid")
        for y in range(0, height, 100):
            self.canvas.create_line(0, y, width, y, fill="lightgray", tags="grid")
    
    def on_resize(self, event):
        self.draw_grid()
    
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.current_rect = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="black", fill="black")
        self.current_text = self.canvas.create_text(event.x, event.y, text="", anchor="nw", font=("Arial", 10), fill='white')

    def on_drag(self, event):
        self.canvas.coords(self.current_rect, self.start_x, self.start_y, event.x, event.y)
        width = abs(event.x - self.start_x)
        height = abs(event.y - self.start_y)
        self.canvas.itemconfig(self.current_text, text=f"{(width)/PX_PER_UM}um x {(height)/PX_PER_UM}um")
        self.canvas.coords(self.current_text, min(self.start_x, event.x) + 5, min(self.start_y, event.y) + 5)

    def on_release(self, event):
        x1, y1, x2, y2 = self.start_x, self.start_y, event.x, event.y
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        self.show_edit_dialog(x1 / PX_PER_UM, y1 / PX_PER_UM, width / PX_PER_UM, height / PX_PER_UM, 1)
        print(self.current_rect)
        print(self.rectangles)
        # self.canvas.create_text(x1 + 5, y1 + 5, text=f"{width}x{height}", anchor="nw", font=("Arial", 24), fill="white")
    
    def show_edit_dialog(self, x=0, y=0, width=1, height=1, index=1, rect=None):
        if rect:
            x,y = [c / PX_PER_UM for c in rect['coords'][0:2]] 
            x2,y2 = [c / PX_PER_UM for c in rect['coords'][2:]] 
            width = (x2 - x)
            height = (y2 - y)
            index = rect['index']
        
        dialog = Toplevel(self.root)
        dialog.title("Edit Rectangle")
        dialog.geometry("250x300")

        tk.Label(dialog, text="X Position:").pack()
        x_entry = tk.Entry(dialog)
        x_entry.insert(0, str(round(x,2)))
        x_entry.pack()

        # print(int(float(x_entry.get()) * PX_PER_UM))
        
        tk.Label(dialog, text="Y Position:").pack()
        y_entry = tk.Entry(dialog)
        y_entry.insert(0, str(round(y,2)))
        y_entry.pack()
        
        tk.Label(dialog, text="Width:").pack()
        width_entry = tk.Entry(dialog)
        width_entry.insert(0, str(round(width,2)))
        width_entry.pack()
        
        tk.Label(dialog, text="Height:").pack()
        height_entry = tk.Entry(dialog)
        height_entry.insert(0, str(round(height,2)))
        height_entry.pack()

        tk.Label(dialog, text="Index:").pack()
        index_entry = tk.Entry(dialog)
        index_entry.insert(0, str(index))
        index_entry.pack()

        def _new_rect():
            x1, y1 = int(float(x_entry.get()) * PX_PER_UM), int(float(y_entry.get()) * PX_PER_UM)
            x2, y2 = int(float(x_entry.get())* PX_PER_UM) + int(float(width_entry.get())* PX_PER_UM), int(float(y_entry.get())* PX_PER_UM) + int(float(height_entry.get())* PX_PER_UM)
            rect = {
                'id': self.current_rect,
                'text_id': self.current_text,
                'coords': (x1,y1,x2,y2),
                'index': float(index_entry.get())
            }
            print("IN DIALOG")
            print(rect)
            return rect

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)

        save_button = tk.Button(btn_frame, text="Save", command=lambda:self.update_rectangle(_new_rect(), dialog))
        save_button.pack(side=tk.LEFT)

        dialog.bind("<Return>", lambda _:self.update_rectangle(_new_rect(), dialog))
        dialog.protocol("WM_DELETE_WINDOW", lambda:self.update_rectangle(_new_rect(), dialog))

        if rect:
            Delete = tk.Button(btn_frame, text="Delete", command=lambda:self.delete_rectangle(self.current_rect, dialog))
            Delete.pack(side=tk.LEFT)

    def delete_rectangle(self, id, dialog: Toplevel | None = None):
        self.canvas.delete(id)
        self.canvas.delete(self.rectangles[id]['text_id'])
        self.rectangles.pop(id, None)
        if dialog:
            dialog.destroy()

    def update_rectangle(self, rectangle: dict, dialog: Toplevel | None = None):
        self.rectangles.update({
            rectangle['id']: {
                'text_id': rectangle['text_id'],
                'coords': rectangle['coords'],
                'index': rectangle['index'],
            } 
        })
        print(self.rectangles)
        self.current_rect = rectangle['id']
        x1, y1 = rectangle['coords'][:2]
        x2, y2 = rectangle['coords'][2:]
        self.canvas.coords(self.current_rect, x1, y1, x2, y2)
        self.canvas.itemconfig(rectangle['text_id'], text=f"{(x2-x1)/PX_PER_UM}um x {(y2-y1)/PX_PER_UM}um, index={rectangle['index']}")
        self.remap_indices()
        self.canvas.coords(rectangle['text_id'], x1 + 5, y1 + 5)
        if dialog: 
            dialog.destroy()

    def add_rectangle_manually(self):
        try:
            self.current_rect = self.canvas.create_rectangle(0,0,0,0,outline="black", fill='black')
            self.current_text = self.canvas.create_text(0,0, text="", anchor="nw", font=("Arial", 10), fill='white')
            self.show_edit_dialog()
        except (TypeError, ValueError):
            pass  # Handle invalid inputs gracefully

    def serialize(self):
        # with open('test.json', 'w') as f:
        #     json.dump(
        #         {
        #             'window': (self.canvas.winfo_width(), self.canvas.winfo_height()),
        #             'rectangles': self.rectangles
        #         },
        #         f
        #     )
        calc = tk.Toplevel(self.root)
        calc.title("Calculating Modes")
        calc.geometry("250x300")
        # progress = ttk.Progressbar(calc, mode='indeterminate')
        # progress.pack()
        # progress.start()
        efields, hfields = calc_modes('test.json')
        # print(np.shape(efields))
        # progress.destroy()
        efield_power = np.asarray(efields[:,:,0,0]**2 + efields[:,:,0,1]**2 + efields[:,:,0,2]**2, dtype=np.uint8)
        # print(np.shape(efield_power))
        # tk_img = ImageTk.PhotoImage(file='mmgc_glass_second_mode_black.png')
        img = Image.fromarray(efield_power, mode='L')
        tk_img = ImageTk.PhotoImage(img)
        label = tk.Label(calc)
        label.config(image=tk_img)
        label.image = tk_img
        # label.image = tk_img
        # print(img)
        # img_frame = tk.Frame(calc).pack()
        label.pack()


    def save_as_svg(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG files", "*.svg")])
        if not file_path:
            return

        dwg = svgwrite.Drawing(file_path, profile='tiny')
        for rect in self.rectangles.values():
            x1, y1, x2, y2 = rect['coords']
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            dwg.add(dwg.rect(insert=(min(x1, x2), min(y1, y2)),
                            size=(width, height),
                            stroke='none', fill='none'))
            # dwg.add(dwg.text(f"{width}x{height}", insert=(min(x1, x2) + 5, min(y1, y2) + 15), font_size="10px"))
        dwg.save()

if __name__ == "__main__":
    if mp.am_really_master():
        root = tk.Tk()
        app = WaveguideDrawer(root)
        root.mainloop()