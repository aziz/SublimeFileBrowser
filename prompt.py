#!/usr/bin/python
# -*- coding: utf-8 -*-

import sublime
from sublime import Region
from sublime_plugin import TextCommand, WindowCommand
import os
from os.path import join, expanduser

ST3 = int(sublime.version()) >= 3000
NT  = sublime.platform() == 'windows'

if ST3:
    from .common import DiredBaseCommand
else:
    from common import DiredBaseCommand

map_window_to_ctx = {}


def start(msg, window, path, callback, *args):
    """
    Starts the prompting process.
    """
    if not(path.endswith(os.sep) or path == os.sep):
        path += os.sep
    path = expanduser(path)
    map_window_to_ctx[window.id()] = PromptContext(msg, path, callback, *args)
    window.run_command('dired_prompt')


def isdir(u):
    '''alas, this is really silly'''
    if NT and any(v for v in (u'\\', u'/') if v == u):
        return False
    else:
        return os.path.isdir(u)


def valid(value):
    if not isdir(value):
        sublime.error_message(u'FileBrowser:\n\nDirectory doesn’t exist:\n%s' % value)
        return False
    else:
        return True


class PromptContext:
    def __init__(self, msg, path, callback, *args):
        self.msg = msg
        self.path = path  # The path we are completing. This is updated as the user types, so it will be an invalid path at times.
        self.callback = callback
        self.args = args


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
        if not valid(value):
            return self.window.run_command('dired_prompt')
        self.ctx.callback(value, *self.ctx.args)


class DiredCompleteCommand(TextCommand, DiredBaseCommand):
    """
    An internal command executed when the user has pressed Tab in our directory prompt.
    """
    def run(self, edit):
        self.edit = edit
        self.prompt_region = Region(0, self.view.size())
        content, path, prefix = self.get_content()
        if not valid(path or content):
            return

        completions, error = self.get_completions(path, prefix)
        if error:
            return  # content of path is unavailable (access, permission, etc.)
        if not completions:
            return sublime.status_message('No matches')

        new_content = self.get_new_content(path, prefix, completions)

        if new_content:
            self.fill_prompt(new_content)
        else:
            self.completions = completions
            self._path = path
            self.w = self.view.window() or sublime.active_window()
            return self.w.show_quick_panel(completions, self.on_done)

    def on_done(self, i):
        if i < 0: return
        content = join(self._path, self.completions[i]) + os.sep
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

    def get_content(self):
        content = expanduser(self.view.substr(self.prompt_region))
        path, prefix = os.path.split(content) if not isdir(content) else (content, '')
        return (content, path, prefix)

    def get_completions(self, path, prefix):
        '''return tuple (completion(list, may be empty), error(boolean))'''
        # self.view is prompt, so get settings of active view in active window
        self.show_hidden = sublime.active_window().active_view().settings().get('dired_show_hidden_files', True)
        dirs, error = self.try_listing_only_dirs(path)
        if error:
            sublime.error_message(u'FileBrowser:\n\n Content is unavailable\n\n\t%s\n\n\t%s' % (path, error))
            return ([], True)
        completions = [n for n in dirs if n.upper().startswith(prefix.upper())]
        return (completions, False)

    def get_new_content(self, path, prefix, completions):
        common = os.path.commonprefix([f.upper() for f in completions])
        if len(completions) == 1:
            new_content = join(path, completions[0]) + os.sep
        elif common and common > prefix:
            new_content = join(path, common)
        else:
            new_content = ''
        return new_content
