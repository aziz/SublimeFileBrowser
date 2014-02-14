import sublime
from sublime import status_message, ok_cancel_dialog, load_settings, save_settings
from sublime_plugin import TextCommand, WindowCommand

import os
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
            msg = "Can't jump to '{0} -> {1}'.\n\nRemove that jump point?".format(name, target)
            if ok_cancel_dialog(msg):
                points = load_jump_points()
                del points[name]
                save_jump_points(points)
                status_message("Jump point '{0}' was removed".format(name))
                self.view.run_command('dired_refresh')


class DiredEditJumpPointCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        self.names = jump_names()
        name = self.names.get(self.path)
        if not name:
            prompt = 'Create jump point:'
            name = basename(self.path[:-1])
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
                    msg =  "The jump point with name '{0}' is already exists ({1})\n\n".format(n, t)
                    msg += "Do you want to overwrite it?"
                    if ok_cancel_dialog(msg):
                        del self.names[t]
                    else:
                        return
            self.names[self.path] = name
            status_message("Jump point for this directory was set to '{0}'".format(name))
        elif self.path in self.names:
            del self.names[self.path]
            status_message("Jump point for this directory was removed")
        else:
            status_message("Jump point wasn't created")
            return
        save_jump_points(self.names, reverse=True)
        self.view.run_command('dired_refresh')