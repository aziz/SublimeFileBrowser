# coding: utf8
import sublime
from sublime import status_message, ok_cancel_dialog, load_settings, save_settings, Region
from sublime_plugin import TextCommand, WindowCommand

import os
import re
from os.path import dirname, realpath, join, isdir, basename, exists

ST3 = int(sublime.version()) >= 3000
if ST3:
    from .common import DiredBaseCommand
    from . import prompt
    from .show import show
else:
    from common import DiredBaseCommand
    import prompt
    from show import show


def load_jump_points():
    return load_settings('dired.sublime-settings').get('dired_jump_points', {})

def save_jump_points(points, reverse=False):
    if reverse:
        points = dict((n, t) for t, n in points.items())
    load_settings('dired.sublime-settings').set('dired_jump_points', points)
    save_settings('dired.sublime-settings')


def jump_points():
    return load_jump_points().items()

def jump_targets():
    return load_jump_points()

def jump_names():
    return dict((t, n) for n, t in load_jump_points().items())


class DiredJumpCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if not jump_points():
            status_message("No jump points available. To create jump point for this directory use 'P'.")
            return
        # show_quick_panel didn't work with dict_items
        self.points = [[n, t] for n, t in jump_points()]
        self.view.window().show_quick_panel(self.points, self.on_pick_point)

    def on_pick_point(self, index):
        if index == -1:
            return
        name, target = self.points[index]
        if exists(target) and isdir(target) and target[-1] == os.sep:
            show(self.view.window(), target, view_id=self.view.id())
            status_message("Jumping to point '{0}' complete".format(name))
        else:
            # workaround ST3 bag https://github.com/SublimeText/Issues/issues/39
            self.view.window().run_command('hide_overlay')
            msg = u"Can't jump to '{0} → {1}'.\n\nRemove that jump point?".format(name, target)
            if ok_cancel_dialog(msg):
                points = load_jump_points()
                del points[name]
                save_jump_points(points)
                status_message(u"Jump point '{0}' was removed".format(name))
                self.view.run_command('dired_refresh')

class DiredEditJumpPointCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, item=False):
        self.names = jump_names()
        self.project_path = item[1] or self.path
        self.item = item
        name = item[0] or self.names.get(self.project_path)
        if not name:
            prompt = 'Create jump point:'
            name = basename(self.project_path[:-1])
        else:
            prompt = 'Edit jump point (clear to Remove):'
        self.view.window().show_input_panel(prompt, name, self.edit_jump_point, None, None)

    def edit_jump_point(self, name):
        if name: # edit or create jump point
            if ST3:
                iterable = list(self.names.items())
            else:
                iterable = self.names.items()
            for t, n in iterable:
                if n == name:
                    msg =  u"The jump point with name '{0}' is already exists ({1})\n\n".format(n, t)
                    msg += "Do you want to overwrite it?"
                    if ok_cancel_dialog(msg):
                        del self.names[t]
                    else:
                        return
            self.names[self.project_path] = name
            status_message(u"Jump point for this directory was set to '{0}'".format(name))
        elif self.project_path in self.names:
            del self.names[self.project_path]
            status_message("Jump point for this directory was removed")
        else:
            status_message("Jump point wasn't created")
            return
        save_jump_points(self.names, reverse=True)
        if self.item:
            self.view.run_command('dired_jump_list', {"reuse": True})
        else:
            self.view.run_command('dired_refresh')


class DiredJumpListRenderCommand(TextCommand):
    def run(self, edit):
        self.view.erase(edit, Region(0, self.view.size()))
        self.view.insert(edit, 0, self.render())
        self.view.sel().clear()
        pt = self.view.text_point(3, 0)
        self.view.sel().clear()
        self.view.sel().add(Region(pt, pt))
        self.view.set_read_only(True)

    def render(self):
        self.view_width = 80
        self.col_padding = 2
        self.points = [[n, t] for n, t in jump_points()]
        self.names = [n for n, t in jump_points()]
        self.max_len_names = max([len(n) for n, t in jump_points()])
        self.view.settings().set('dired_project_count', len(self.names))
        content = "Jump to…\n" + "—"*self.view_width + "\n\n"
        for p in self.points:
            content += u'★ {0}❯{1}\n'.format(self.display_name(p[0]), self.display_path(p[1]))
        return content

    def display_name(self, name):
        return name + " " * (self.max_len_names - len(name) + self.col_padding)

    def display_path(self, folder):
        display = folder
        home = os.path.expanduser("~")
        label_characters = self.view_width - 3 - (self.col_padding*2) - self.max_len_names
        if folder.startswith(home):
            display = folder.replace(home, "~", 1)
        if len(display) > label_characters:
            chars = int(label_characters/2)
            display = display[:chars] + "…" + display[-chars:]
        return " " * self.col_padding + display


class DiredJumpListCommand(TextCommand):
    def run(self, edit, reuse=False):
        if reuse:
            view = self.view
            view.set_read_only(False)
        else:
            view = self.view.window().new_file()

        view.set_name("FileBrowser: Jump List")
        view.set_scratch(True)
        view.set_syntax_file('Packages/FileBrowser/dired.hidden-tmLanguage')
        view.settings().set('color_scheme','Packages/FileBrowser/dired.hidden-tmTheme')
        view.settings().set('line_numbers', False)
        view.settings().set('draw_centered', True)
        view.run_command('dired_jump_list_render')
        sublime.active_window().focus_view(view)


class DiredProjectNextLineCommand(TextCommand):
    def run(self, edit, forward=None):
        assert forward in (True, False), 'forward must be set to True or False'

        count = self.view.settings().get('dired_project_count', 0)
        files = Region(self.view.text_point(3, 0), self.view.text_point(count+3-1, 0))

        if files.empty():
            return

        pt = self.view.sel()[0].a

        if files.contains(pt):
            # Try moving by one line.
            line = self.view.line(pt)
            pt = forward and (line.b + 1) or (line.a - 1)

        if not files.contains(pt):
            # Not (or no longer) in the list of files, so move to the closest edge.
            pt = (pt > files.b) and files.b or files.a

        # print(pt)
        line = self.view.line(pt)
        self.view.sel().clear()
        self.view.sel().add(Region(line.a, line.a))


class DiredProjectSelectCommand(TextCommand):
    def run(self, edit):
        pt = self.view.sel()[0].a
        row, col = self.view.rowcol(pt)
        points = [[n, t] for n, t in jump_points()]
        current_project = [points[row - 3][1]]
        self.view.run_command("dired_open_in_new_window", { "project_folder": current_project})
        sublime.set_timeout(lambda: self.view.close(), 100)


class DiredProjectEditJumpPointCommand(TextCommand):
    def run(self, edit):
        pt = self.view.sel()[0].a
        row, col = self.view.rowcol(pt)
        points = [[n, t] for n, t in jump_points()]
        current_project = points[row - 3]
        self.view.run_command("dired_edit_jump_point", { "item": current_project})
