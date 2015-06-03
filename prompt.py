#!/usr/bin/python
# -*- coding: utf-8 -*-

import sublime
from sublime import Region
from sublime_plugin import TextCommand, WindowCommand
import os
from os.path import join, isdir, expanduser

ST3 = int(sublime.version()) >= 3000

if ST3:
    from .common import sort_nicely
else:
    from common import sort_nicely

map_window_to_ctx = {}


def start(msg, window, path, callback):
    """
    Starts the prompting process.
    """
    if not(path.endswith(os.sep) or path == os.sep):
        path += os.sep
    path = expanduser(path)
    map_window_to_ctx[window.id()] = PromptContext(msg, path, callback)
    window.run_command('dired_prompt')


class PromptContext:
    def __init__(self, msg, path, callback):
        self.msg = msg
        self.path = path  # The path we are completing. This is updated as the user types, so it will be an invalid path at times.
        self.callback = callback


class DiredPromptCommand(WindowCommand):
    """
    An internal-only command that separates prompt handling from external commands since each
    tab completion requires another command.
    A prompt context must already be registered in map_window_to_ctx when this is executed.
    """
    def run(self):
        self.ctx = ctx = map_window_to_ctx[self.window.id()]
        pv = self.window.show_input_panel(ctx.msg, ctx.path, self.on_done, None, None)
        pv.settings().set('dired_prompt', True)

    def on_done(self, value):
        self.ctx.callback(value)


class DiredCompleteCommand(TextCommand):
    """
    An internal command executed when the user has pressed Tab in our directory prompt.
    """
    def run(self, edit):
        self.edit = edit
        self.prompt_region = Region(0, self.view.size())
        content = expanduser(self.view.substr(self.prompt_region))
        path, prefix = os.path.split(content)
        if not isdir(path):
            return sublime.error_message(u'Invalid:\n\n%s', content)

        completions = [n for n in os.listdir(path) if n.startswith(prefix) and isdir(join(path, n))]
        sort_nicely(completions)
        common      = os.path.commonprefix(completions)
        new_content = ''

        if not completions:
            return sublime.status_message('No matches')

        if len(completions) == 1:
            new_content = join(path, completions[0]) + os.sep
        elif common and common > prefix:
            new_content = join(path, common)

        if new_content:
            self.fill_prompt(new_content)
        else:
            self.completions = completions
            self.path = path
            self.w = self.view.window() or sublime.active_window()
            return self.w.show_quick_panel(completions, self.on_done)

    def on_done(self, i):
        if i < 0: return
        content = join(self.path, self.completions[i]) + os.sep
        if ST3:
            ctx = map_window_to_ctx.get(self.w.id())
            ctx.path = content
            self.w.run_command('dired_prompt')
            return
        else:
            self.fill_prompt(content)
            self.w.focus_view(self.view)

    def fill_prompt(self, new_content):
        self.view.replace(self.edit, self.prompt_region, new_content)
        eol = self.view.size()
        self.view.sel().clear()
        self.view.sel().add(Region(eol, eol))
        return
